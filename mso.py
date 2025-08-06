import logging
import asyncio
import json
import re
from enum import Enum
from agents import Agent, Runner, trace, function_tool, SQLiteSession
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import os

#Userdefine Modules Import
from instructions_template import (
    msoAgent_instructions,
    routingDirectorAgent_instructions,
    routingDirector_description,
    apstraAgent_instructions,
    apstra_description,
    securityDirectorAgent_instructions,
    securityDirector_description,
    detailsFillerAgent_instructions
    )

load_dotenv(override=True)
logger = logging.getLogger(__name__)

class AgentType(Enum):
    """Agent types in the IAAS system"""
    APSTRA = "apstra"
    SECURITY_DIRECTOR = "security_director"
    ROUTING_DIRECTOR = "routing_director"
    JUNOS = "junos_agent"

class msoAgentOutput(BaseModel):
    agent_name: str = Field(
        default = None,
        description= "You should select the correct agent/tool to call based on user query"
    )

class InterfaceConfig(BaseModel):
    """Configuration for network interface"""
    interface_type: str  # "tagged" or "untagged"
    site_id: str
    network_access_id: str
    # Tagged interface fields (for untagged_interface section)
    speed: Optional[str] = None
    lldp: Optional[bool] = None
    oam_enabled: Optional[bool] = None
    # Untagged interface fields (for tagged_interface section)
    cvlan_id: Optional[int] = None

class JsonDetailsCollector:
    """Handles extraction and collection of missing details from JSON with placeholders"""
    
    def __init__(self):
        self.interface_configs = {}  # site_id -> InterfaceConfig
        self.current_json = None
        
    def extract_interface_requirements(self, json_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract sites that need interface configuration"""
        sites_info = []
        
        if not json_data:
            return sites_info
            
        try:
            if "l2vpn_svc" in json_data and json_data["l2vpn_svc"] and "sites" in json_data["l2vpn_svc"]:
                sites = json_data["l2vpn_svc"]["sites"]["site"]
                
                for site in sites:
                    if not site:
                        continue
                        
                    site_id = site.get("site_id")
                    if "site_network_accesses" in site and site["site_network_accesses"]:
                        accesses = site["site_network_accesses"]["site_network_access"]
                        if accesses:
                            for access in accesses:
                                if not access:
                                    continue
                                    
                                network_access_id = access.get("network_access_id")
                                country_info = {}
                                
                                if site.get("locations") and site["locations"].get("location"):
                                    locations = site["locations"]["location"]
                                    if locations and len(locations) > 0:
                                        country_info = locations[0]
                                
                                sites_info.append({
                                    "site_id": site_id or "unknown_site",
                                    "network_access_id": network_access_id or "unknown_access",
                                    "country_code": country_info.get("country_code", "")
                                })
        except (TypeError, KeyError, IndexError) as e:
            logger.error(f"Error extracting interface requirements: {e}")
        
        return sites_info
    
    def create_final_json(self, original_json: Dict[str, Any]) -> Dict[str, Any]:
        """Create final JSON with user-provided interface configurations"""
        final_json = json.loads(json.dumps(original_json))  # Deep copy
        
        # Navigate to sites and update configurations
        if "l2vpn_svc" in final_json and "sites" in final_json["l2vpn_svc"]:
            sites = final_json["l2vpn_svc"]["sites"]["site"]
            
            for site in sites:
                site_id = site.get("site_id")
                if site_id in self.interface_configs:
                    config = self.interface_configs[site_id]
                    
                    # Update site_network_accesses
                    if "site_network_accesses" in site:
                        accesses = site["site_network_accesses"]["site_network_access"]
                        for access in accesses:
                            if access.get("network_access_id") == config.network_access_id:
                                self._update_connection_config(access["connection"], config)
        
        return final_json
    
    def _update_connection_config(self, connection: Dict[str, Any], config: InterfaceConfig):
        """Update connection configuration based on interface type"""
        
        # Set ethernet interface type
        connection["eth_inf_type"] = config.interface_type
        
        if config.interface_type == "tagged":
            # For tagged interfaces, populate untagged_interface section
            connection["untagged_interface"] = {
                "lldp": config.lldp,
                "oam_802.3ah_link": {
                    "enabled": config.oam_enabled
                },
                "speed": config.speed
            }
            # Remove tagged interface
            if "tagged_interface" in connection:
                del connection["tagged_interface"]
                
        elif config.interface_type == "untagged":
            # For untagged interfaces, populate tagged_interface section
            connection["tagged_interface"] = {
                "dot1q_vlan_tagged": {
                    "cvlan_id": config.cvlan_id,
                    "tg_type": "c-vlan"
                },
                "type": "dot1q"
            }
            # Remove untagged interface
            if "untagged_interface" in connection:
                del connection["untagged_interface"]

class msoAgentClass():
    def __init__(self):
        self.model = "gpt-4o"
        self.routing_director_params = {
            "command": "uv", 
            "args": ["run", "mcpServers/RoutingDirector/rdMCPServer.py"],
            "max_retries":0}
        
        # Create sessions directory if it doesn't exist
        self.sessions_dir = Path("sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        
        # Create payload directory if it doesn't exist
        self.payload_dir = Path("payload")
        self.payload_dir.mkdir(exist_ok=True)
        
        # Dictionary to store active sessions
        self.active_sessions = {}
        
        # JSON details collector for interface configuration
        self.json_collector = JsonDetailsCollector()

    def get_or_create_session(self, session_id: str):
        """Get existing session or create a new one"""
        if session_id not in self.active_sessions:
            session_file = self.sessions_dir / f"{session_id}.db"
            self.active_sessions[session_id] = SQLiteSession(str(session_file))
        return self.active_sessions[session_id]

    async def save_final_json_configuration(self, json_config: Dict[str, Any], session_id: str) -> str:
        """Save final JSON configuration to payload directory with service_type_hostname1_hostname2_timestamp.json format"""
        if not json_config:
            logger.error("No JSON config provided for saving")
            return "Error: No configuration to save"
            
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Extract service type and hostnames from JSON
            service_type = "unknown_service"
            hostnames = []
            
            # Try to extract service type from design_id
            if "design_id" in json_config and json_config["design_id"]:
                service_type = json_config["design_id"].replace("-", "_")
                logger.info(f"Extracted service_type from design_id: {service_type}")
            elif "l2vpn_svc" in json_config:
                service_type = "l2vpn_service"
                logger.info(f"Using default service_type: {service_type}")
            
            # Extract hostnames from sites
            if ("l2vpn_svc" in json_config and json_config["l2vpn_svc"] and 
                "sites" in json_config["l2vpn_svc"] and json_config["l2vpn_svc"]["sites"]):
                sites = json_config["l2vpn_svc"]["sites"]["site"]
                if sites:
                    for site in sites:
                        if site and "site_id" in site and site["site_id"]:
                            hostnames.append(site["site_id"])
                logger.info(f"Extracted hostnames: {hostnames}")
            
            # Create filename with format: service_type_hostname1_hostname2_timestamp.json
            if len(hostnames) >= 2:
                filename = f"{service_type}_{hostnames[0]}_{hostnames[1]}_{timestamp}.json"
            elif len(hostnames) == 1:
                filename = f"{service_type}_{hostnames[0]}_single_site_{timestamp}.json"
            else:
                filename = f"{service_type}_no_hostnames_{timestamp}.json"
            
            filepath = self.payload_dir / filename
            logger.info(f"Saving final JSON to: {filepath}")
            
            # Save JSON with pretty formatting
            with open(filepath, 'w') as f:
                json.dump(json_config, f, indent=2)
            
            logger.info(f"Final JSON configuration saved successfully to: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving final JSON configuration: {e}")
            return f"Error saving configuration: {str(e)}"

    async def close_session(self, session_id: str):
        """Close and cleanup a session"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            # Close the session if it has a close method
            if hasattr(session, 'close'):
                await session.close()
            del self.active_sessions[session_id]

    async def msoAgent(self, message: str, session_id: str = "default_session"):
        """
        Main MSO Agent method with memory support and conversational interface configuration
        
        Args:
            message: User's input message
            session_id: Unique identifier for the conversation session
        """
        # Get or create session for this conversation
        session = self.get_or_create_session(session_id)
        
        logger.info(f"msoAgent Triggered for session: {session_id}")
        
        # Keep MCP server connection alive during the entire execution
        async with MCPServerStdio(params=self.routing_director_params, client_session_timeout_seconds=120) as rd_svcs_mcp:
            rd_agent, apstra_agent, sd_agent = await self.create_specialist_agent(rd_svcs_mcp)
            tool1 = rd_agent.as_tool(tool_name="rd_agent", tool_description=routingDirector_description())
            tool2 = apstra_agent.as_tool(tool_name="apstra_agent", tool_description=apstra_description())
            tool3 = sd_agent.as_tool(tool_name="sd_agent", tool_description=securityDirector_description())
            
            # Create the save JSON tool with session context
            @function_tool
            async def save_json_to_payload() -> str:
                """Save the last JSON configuration from conversation to payload directory"""
                # This will be called for general JSON saving from other agents
                try:
                    # Get the session to access conversation history
                    session_obj = self.get_or_create_session(session_id)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"general_config_{session_id[:8]}_{timestamp}.json"
                    filepath = self.payload_dir / filename
                    
                    # This is a placeholder for general JSON saving
                    return f"General JSON configuration save location: {filepath}"
                    
                except Exception as e:
                    logger.error(f"Error in save_json_to_payload: {e}")
                    return f"Error saving configuration: {str(e)}"

            tools = [tool1, tool2, tool3, save_json_to_payload]
            
            msoAgent = Agent(
                    name="msoAgent", 
                    instructions=msoAgent_instructions(), 
                    model=self.model,
                    tools=tools)
            
            # Use tracing with group_id for better organization
            with trace(workflow_name="SANDMAN_Conversation", group_id=session_id):
                # Run agent with session memory - automatically maintains conversation history
                result = await Runner.run(msoAgent, message, session=session)
                logger.info(f"****** msoAgent final output: {result.final_output}")
                
                # Check if the result contains JSON with placeholders
                json_config = None
                if result and hasattr(result, 'final_output') and result.final_output:
                    json_config = self._extract_json_from_output(result.final_output)
                
                if json_config and self._has_interface_placeholders(json_config):
                    logger.info("Found interface placeholders, starting conversational configuration...")
                    
                    # Store the JSON for the details filler agent
                    self.json_collector.current_json = json_config
                    
                    # Create and run details filler agent
                    dt_filler_agent = await self.create_details_filler_agent(json_config, session, session_id)
                    
                    # Start the conversational interface configuration
                    config_result = await Runner.run(
                        dt_filler_agent, 
                        "Please help me configure the network interfaces for each site by asking the user for the missing details.", 
                        session=session
                    )
                    
                    if config_result and hasattr(config_result, 'final_output'):
                        return config_result.final_output
                    else:
                        return "Configuration completed but no output received."
                else:
                    if result and hasattr(result, 'final_output'):
                        try:
                            final_json = self.json_collector.create_final_json(json_config)
                            filepath = await self.save_final_json_configuration(final_json, session_id=session_id)
                            saved_filename = os.path.basename(filepath)
                            logger.info(f"\n\n💾 Configuration automatically saved to: {saved_filename}")

                        except Exception as save_error:
                            logger.error(f"Auto-save failed: {save_error}")
                        return result.final_output
                    else:
                        return "No output received from agent."

    def _extract_json_from_output(self, output: str) -> Dict[str, Any]:
        """Extract JSON configuration from agent output"""
        if not output:
            return None
            
        try:    
            # Fallback to regex extraction
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                if json_str:
                    return json.loads(json_str)
            
            # Try to find JSON without code blocks
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                if json_str:
                    return json.loads(json_str)
                
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse JSON: {e}")
            
        return None
    
    def _has_interface_placeholders(self, json_data: Dict[str, Any]) -> bool:
        """Check if JSON contains interface-related placeholders"""
        if not json_data:
            return False
            
        try:
            json_str = json.dumps(json_data)
            if not json_str:
                return False
                
            interface_placeholders = [
                "{ETHERNET_INTF_TYPE}", "{CVLAN_ID}", "{LLDP_BOOLEAN}", 
                "{OAM_ENABLED_BOOLEAN}", "{SPEED}"
            ]
            return any(placeholder in json_str for placeholder in interface_placeholders)
        except (TypeError, ValueError) as e:
            logger.error(f"Error checking interface placeholders: {e}")
            return False

    async def create_details_filler_agent(self, json_config: Dict[str, Any], session, session_id: str = None):
        """Create details filler agent with conversational interface configuration tools"""
        
        # Extract sites that need configuration
        sites_info = self.json_collector.extract_interface_requirements(json_config)
        
        # Create context for the agent
        context = self._create_agent_context(sites_info, json_config)
        
        # Create tools for the details filler agent
        @function_tool 
        async def set_interface_type(site_id: str, network_access_id: str, interface_type: str) -> str:
            """Set the interface type for a specific site"""
            
            if interface_type.lower() not in ["tagged", "untagged"]:
                return "Error: Interface type must be 'tagged' or 'untagged'"
            
            interface_type = interface_type.lower()
            
            # Initialize or update interface config
            if site_id not in self.json_collector.interface_configs:
                self.json_collector.interface_configs[site_id] = InterfaceConfig(
                    interface_type=interface_type,
                    site_id=site_id,
                    network_access_id=network_access_id
                )
            else:
                self.json_collector.interface_configs[site_id].interface_type = interface_type
            
            next_step = "speed, LLDP, and OAM settings" if interface_type == "tagged" else "CVLAN ID"
            return f"✅ Site {site_id} configured as {interface_type} interface. Next: collect {next_step}"

        @function_tool
        async def set_tagged_config(site_id: str, speed: str, lldp: bool, oam_enabled: bool) -> str:
            """Set configuration for tagged interface (speed, lldp, oam)"""
            
            if site_id not in self.json_collector.interface_configs:
                return f"Error: Interface type not set for site {site_id}. Please set interface type first."
            
            config = self.json_collector.interface_configs[site_id]
            
            if config.interface_type != "tagged":
                return f"Error: Site {site_id} is not configured as tagged interface"
            
            # Validate speed
            if not speed.isdigit():
                return "Error: Speed must be a numeric value (e.g., 1000, 10000)"
            
            # Update configuration
            config.speed = speed
            config.lldp = lldp
            config.oam_enabled = oam_enabled
            
            return f"✅ Tagged interface configuration set for {site_id}: Speed={speed}, LLDP={lldp}, OAM={oam_enabled}"

        @function_tool
        async def set_untagged_config(site_id: str, cvlan_id: int) -> str:
            """Set configuration for untagged interface (cvlan_id)"""
            
            if site_id not in self.json_collector.interface_configs:
                return f"Error: Interface type not set for site {site_id}. Please set interface type first."
            
            config = self.json_collector.interface_configs[site_id]
            
            if config.interface_type != "untagged":
                return f"Error: Site {site_id} is not configured as untagged interface"
            
            # Validate CVLAN ID
            if not (1 <= cvlan_id <= 4094):
                return "Error: CVLAN ID must be between 1 and 4094"
            
            # Update configuration
            config.cvlan_id = cvlan_id
            
            return f"✅ Untagged interface configuration set for {site_id}: CVLAN ID={cvlan_id}"

        @function_tool
        async def get_configuration_status() -> str:
            """Get current configuration status for all sites"""
            
            status_lines = ["📊 Configuration Status:"]
            
            for site_info in sites_info:
                site_id = site_info["site_id"]
                country = site_info["country_code"]
                
                if site_id in self.json_collector.interface_configs:
                    config = self.json_collector.interface_configs[site_id]
                    
                    if self._is_config_complete(config):
                        status_lines.append(f"✅ {site_id} ({country}): {config.interface_type} - COMPLETE")
                        
                        if config.interface_type == "tagged":
                            status_lines.append(f"   Speed: {config.speed}, LLDP: {config.lldp}, OAM: {config.oam_enabled}")
                        else:
                            status_lines.append(f"   CVLAN ID: {config.cvlan_id}")
                    else:
                        missing = self._get_missing_fields(config)
                        status_lines.append(f"⏳ {site_id} ({country}): {config.interface_type} - Missing: {', '.join(missing)}")
                else:
                    status_lines.append(f"❌ {site_id} ({country}): Interface type not set")
            
            return "\n".join(status_lines)

        @function_tool
        async def finalize_configuration() -> str:
            """Generate final JSON configuration with all interface settings and auto-save"""
            
            try:
                # Check if all sites are configured
                all_complete = True
                for site_info in sites_info:
                    site_id = site_info["site_id"]
                    if site_id not in self.json_collector.interface_configs:
                        all_complete = False
                        break
                    
                    config = self.json_collector.interface_configs[site_id]
                    if not self._is_config_complete(config):
                        all_complete = False
                        break
                
                if not all_complete:
                    return "❌ Cannot finalize: Some sites are not fully configured. Use get_configuration_status to check."
                
                # Generate final JSON
                final_json = self.json_collector.create_final_json(json_config)
                json_str = json.dumps(final_json, indent=2)
                
                # Auto-save to payload directory
                try:
                    current_session_id = session_id or "unknown_session"
                    filepath = await self.save_final_json_configuration(final_json, current_session_id)
                    saved_filename = os.path.basename(filepath)
                    save_msg = f"\n\n💾 Configuration automatically saved to: {saved_filename}"
                except Exception as save_error:
                    logger.error(f"Auto-save failed: {save_error}")
                    save_msg = "\n\n⚠️ Note: Auto-save failed, but configuration is complete."
                
                return f"🎉 Configuration completed successfully!```json\n{json_str}\n```"
                
            except Exception as e:
                logger.error(f"Error finalizing configuration: {e}")
                return f"❌ Error generating final configuration: {str(e)}"

        # Create the details filler agent with tools
        tools = [set_interface_type, set_tagged_config, set_untagged_config, get_configuration_status, finalize_configuration]
        
        enhanced_instructions = detailsFillerAgent_instructions() + f"\n\n{context}"
        
        dt_filler_agent = Agent(
            name="Network Interface Configuration Assistant",
            instructions=enhanced_instructions,
            model=self.model,
            tools=tools
        )
        
        return dt_filler_agent

    def _create_agent_context(self, sites_info: List[Dict[str, str]], json_config: Dict[str, Any]) -> str:
        """Create context information for the details filler agent"""
        context = "🌐 CURRENT CONFIGURATION CONTEXT:\n\n"
        context += f"Found {len(sites_info)} sites requiring interface configuration:\n"
        
        for i, site in enumerate(sites_info, 1):
            context += f"{i}. Site: {site['site_id']} ({site['country_code']})\n"
            context += f"   Network Access: {site['network_access_id']}\n"
        
        context += "\n📋 CONFIGURATION WORKFLOW:\n"
        context += "1. For each site, ask user to choose interface type: 'tagged' or 'untagged'\n"
        context += "2. If UNTAGGED: collect speed (Mbps), LLDP (true/false), OAM (true/false)\n"  
        context += "3. If TAGGED: collect CVLAN ID (1-4094)\n"
        context += "4. Based on selected TAGGED or UNTAGGED keep only that hierarchy in JSON remove the other one\n"
        context += "5. Use tools to validate and store configurations\n"
        context += "6. Generate final JSON when all sites are configured\n"
        
        context += "\n🛠️ AVAILABLE TOOLS:\n"
        context += "- set_interface_type(site_id, network_access_id, interface_type)\n"
        context += "- set_tagged_config(site_id, speed, lldp, oam_enabled) \n"
        context += "- set_untagged_config(site_id, cvlan_id)\n"
        context += "- get_configuration_status()\n"
        context += "- finalize_configuration()\n"
        
        return context
    
    def _is_config_complete(self, config: InterfaceConfig) -> bool:
        """Check if interface configuration is complete"""
        if config.interface_type == "tagged":
            return all([config.speed, config.lldp is not None, config.oam_enabled is not None])
        elif config.interface_type == "untagged":
            return config.cvlan_id is not None
        return False
    
    def _get_missing_fields(self, config: InterfaceConfig) -> List[str]:
        """Get list of missing configuration fields"""
        missing = []
        
        if config.interface_type == "tagged":
            if not config.speed:
                missing.append("speed")
            if config.lldp is None:
                missing.append("lldp")
            if config.oam_enabled is None:
                missing.append("oam_enabled")
        elif config.interface_type == "untagged":
            if config.cvlan_id is None:
                missing.append("cvlan_id")
        
        return missing

    async def create_specialist_agent(self, rd_svcs_mcp):
        """Create specialist agents for routing, apstra, and security"""
        rd_agent = Agent(
            name="routing director agent", 
            instructions=routingDirectorAgent_instructions(), 
            model=self.model,
            mcp_servers= [rd_svcs_mcp]
            )
        
        apstra_agent =  Agent(
            name="apstra agent", 
            instructions=apstraAgent_instructions(), 
            model=self.model)
        
        sd_agent  = Agent(
            name="security director agent",
            instructions=securityDirectorAgent_instructions(), 
            model=self.model)
        
        return rd_agent, apstra_agent, sd_agent

    # Session management methods for GUI integration
    async def get_session_summary(self, session_id: str) -> Dict:
        """Get session summary information"""
        try:
            session = self.get_or_create_session(session_id)
            # Implementation depends on your SQLiteSession structure
            # This is a placeholder - you'll need to implement based on your session structure
            return {
                "session_id": session_id,
                "exists": session_id in self.active_sessions,
                "total_messages": 0,  # Implement based on your session structure
                "user_messages": 0,
                "assistant_messages": 0
            }
        except Exception as e:
            logger.error(f"Error getting session summary: {e}")
            return {"session_id": session_id, "exists": False, "error": str(e)}

    async def get_conversation_history(self, session_id: str, limit: int = None) -> List[Dict]:
        """Get conversation history from agent memory"""
        try:
            session = self.get_or_create_session(session_id)
            # Implementation depends on your SQLiteSession structure
            # This is a placeholder - you'll need to implement based on your session structure
            return []
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

    async def clear_conversation_history(self, session_id: str) -> bool:
        """Clear conversation history for a session"""
        try:
            if session_id in self.active_sessions:
                await self.close_session(session_id)
                # Remove the session file
                session_file = self.sessions_dir / f"{session_id}.db"
                if session_file.exists():
                    session_file.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Error clearing session history: {e}")
            return False

    async def list_active_sessions(self) -> List[str]:
        """List all active sessions"""
        try:
            return list(self.active_sessions.keys())
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return []
    
    def extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON from response for GUI display"""
        return self._extract_json_from_output(response)

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup all sessions"""
        for session_id in list(self.active_sessions.keys()):
            await self.close_session(session_id)

async def main():
    # Example usage with session memory
    async with msoAgentClass() as mso:
        logger.info(f"mso {mso}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())