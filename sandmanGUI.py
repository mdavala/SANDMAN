import streamlit as st
import asyncio
import json
import uuid
import re
from datetime import datetime
import logging
from typing import Dict, Any

from mso import msoAgentClass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Streamlit page
st.set_page_config(
    page_title="SANDMAN - Multi-Agent Service Orchestrator",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for styling
st.markdown("""
<style>
.chat-message {
    padding: 10px;
    margin: 5px 0;
    border-radius: 5px;
}
.user-message {
    background-color: #1f77b4;
    color: white;
    border-left: 4px solid #0d47a1;
}
.assistant-message {
    background-color: #ff7f0e;
    color: white;
    border-left: 4px solid #e65100;
}
.agent-info {
    background-color: #2ca02c;
    color: white;
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
}

.header-section {
    background: linear-gradient(90deg, #1f77b4 0%, #ff7f0e 100%);
    padding: 20px;
    border-radius: 10px;
    color: white;
    text-align: center;
    margin-bottom: 20px;
}

.agent-status {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 15px;
    font-size: 0.8rem;
    margin: 2px;
}

.agent-apstra {
    background-color: #9c27b0;
    color: white;
}

.agent-routing {
    background-color: #2196f3;
    color: white;
}

.agent-security {
    background-color: #f44336;
    color: white;
}

.session-info {
    background-color: #1f77b4;
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
    border-left: 4px solid #4caf50;
}

.config-status {
    background-color: #e8f5e8;
    color: #2e7d32;
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
    border-left: 4px solid #4caf50;
}

.interface-help {
    background-color: #fff3e0;
    color: #ef6c00;
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
    border-left: 4px solid #ff9800;
}
</style>
""", unsafe_allow_html=True)


class sandmanGUI:
    def __init__(self):
        self.mso_agent = msoAgentClass()

    async def send_message(self, message: str, session_id: str):
        """Send message to MSO Agent with session memory and conversational interface configuration"""
        try:
            logger.info(f"****** message {message} session_id {session_id} in sandman gui send message")
            result = await self.mso_agent.msoAgent(message=message, session_id=session_id)
            logger.info(f'Result for session {session_id}: {result}')
            return result
        except Exception as e:
            logger.error(f"Error in sandmanGUI.send_message: {str(e)}")
            return f"Error processing request: {str(e)}"

    async def get_session_summary(self, session_id: str):
        """Get session summary information"""
        try:
            return await self.mso_agent.get_session_summary(session_id)
        except Exception as e:
            logger.error(f"Error getting session summary: {str(e)}")
            return {"session_id": session_id, "exists": False, "error": str(e)}

    async def clear_session_history(self, session_id: str):
        """Clear conversation history for a session"""
        try:
            return await self.mso_agent.clear_conversation_history(session_id)
        except Exception as e:
            logger.error(f"Error clearing session history: {str(e)}")
            return False

    def extract_json_from_response(self, response: str):
        """Extract JSON from response for display"""
        return self.mso_agent.extract_json_from_response(response)


def run_async(coro):
    """Helper function to run async functions in Streamlit"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def initialize_session_state():
    """Initialize Streamlit session state with memory support"""
    if 'sandman_client' not in st.session_state:
        st.session_state.sandman_client = sandmanGUI()
    
    # Generate unique session ID for this browser session if not exists
    if 'session_id' not in st.session_state:
        st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Generated new session ID: {st.session_state.session_id}")
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
        
    if 'agent_stats' not in st.session_state:
        st.session_state.agent_stats = {
            'total_queries': 0,
            'routing_director_calls': 0,
            'security_director_calls': 0,
            'apstra_calls': 0,
            'interface_configs_completed': 0
        }
        
    if 'session_summary' not in st.session_state:
        st.session_state.session_summary = {}


def display_agent_status():
    """Display agent status information with session details"""
    st.markdown("""
    <div class="header-section">
        <h2>🏗️ SANDMAN Multi-Agent Orchestrator</h2>
        <p>Intelligent Infrastructure as a Service (IAAS) Management System with Conversational Interface Configuration</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Session information
    session_id = st.session_state.session_id
    try:
        session_summary = run_async(st.session_state.sandman_client.get_session_summary(session_id))
        st.session_state.session_summary = session_summary
    except Exception as e:
        logger.error(f"Error getting session summary: {e}")
        session_summary = {"session_id": session_id, "exists": False, "total_messages": 0}
    
    # Display session info
    # st.markdown(f"""
    # <div class="session-info">
    #     <strong>🧠 Session Memory:</strong> {session_id[:16]}... | 
    #     <strong>Messages:</strong> {session_summary.get('total_messages', 0)} | 
    #     <strong>Status:</strong> {'Active' if session_summary.get('exists', False) else 'New'}
    # </div>
    # """, unsafe_allow_html=True)
    
    # Agent status indicators
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="agent-status agent-routing">
            🌐 Routing Director<br>
            <small>Network Services</small>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="agent-status agent-security">
            🔒 Security Director<br>
            <small>Security Policies</small>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="agent-status agent-apstra">
            📊 Apstra Agent<br>
            <small>Data Center Fabric</small>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        stats = st.session_state.agent_stats
        st.metric(
            label="Total Queries",
            value=stats['total_queries'],
            delta=None
        )

def is_final_json_message(message: str) -> bool:
    """Check if message contains final JSON configuration"""
    is_final = "🎉 Configuration completed successfully!" in message and "```json" in message
    if is_final:
        logger.info("Detected final JSON message")
    return is_final

def extract_final_json_from_message(message: str) -> Dict[str, Any]:
    """Extract final JSON configuration from completion message"""
    try:
        # Look for JSON within ```json blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', message, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            return json.loads(json_str)
        
        # Fallback: try to find any JSON object in the message
        json_match = re.search(r'\{[\s\S]*\}', message)
        if json_match:
            json_str = json_match.group(0).strip()
            return json.loads(json_str)
            
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to extract final JSON: {e}")
    return None

def generate_download_filename(json_config: Dict[str, Any]) -> str:
    """Generate filename in format: service_type_hostname1_hostname2_timestamp.json"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Extract service type and hostnames from JSON
    service_type = "unknown_service"
    hostnames = []
    
    try:
        # Try to extract service type from design_id
        if json_config and "design_id" in json_config:
            service_type = json_config["design_id"].replace("-", "_")
        elif json_config and "l2vpn_svc" in json_config:
            service_type = "l2vpn_service"
        
        # Extract hostnames from sites
        if json_config and "l2vpn_svc" in json_config and "sites" in json_config["l2vpn_svc"]:
            sites = json_config["l2vpn_svc"]["sites"]["site"]
            for site in sites:
                if "site_id" in site:
                    hostnames.append(site["site_id"])
                    
        logger.info(f"Generated filename components: service_type={service_type}, hostnames={hostnames}")
        
    except Exception as e:
        logger.error(f"Error generating filename: {e}")
        service_type = "error_service"
    
    # Create filename with format: service_type_hostname1_hostname2_timestamp.json
    if len(hostnames) >= 2:
        filename = f"{service_type}_{hostnames[0]}_{hostnames[1]}_{timestamp}.json"
    elif len(hostnames) == 1:
        filename = f"{service_type}_{hostnames[0]}_single_site_{timestamp}.json"
    else:
        filename = f"{service_type}_no_hostnames_{timestamp}.json"
    
    logger.info(f"Generated download filename: {filename}")
    return filename

def is_configuration_message(message: str) -> bool:
    """Check if message contains configuration status or instructions"""
    config_indicators = [
        "✅", "❌", "⏳", "🎉", "📊", "Configuration Status",
        "interface type", "tagged", "untagged", "CVLAN", "speed", "LLDP", "OAM"
    ]
    return any(indicator in message for indicator in config_indicators)


def display_chat_history():
    """Display chat history from Streamlit session state"""
    for i, chat in enumerate(st.session_state.chat_history):
        timestamp = chat.get('timestamp', '')
        user_msg = chat.get('user_message', '')
        assistant_msg = chat.get('assistant_message', '')
        json_config = chat.get('json_config', None)
        
        if user_msg:
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>You:</strong> {user_msg}
                <br><small>{timestamp}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if assistant_msg:
            # Clean up any broken formatting
            clean_msg = assistant_msg.strip()
            
            # Try to detect which agent was likely used based on response content
            agent_indicator = ""
            if "routing director" in clean_msg.lower() or "evpn" in clean_msg.lower() or "l3vpn" in clean_msg.lower():
                agent_indicator = "🌐 Routing Director"
                st.session_state.agent_stats['routing_director_calls'] += 1
            elif "security director" in clean_msg.lower() or "firewall" in clean_msg.lower() or "policy" in clean_msg.lower():
                agent_indicator = "🔒 Security Director"
                st.session_state.agent_stats['security_director_calls'] += 1
            elif "apstra" in clean_msg.lower() or "fabric" in clean_msg.lower():
                agent_indicator = "📊 Apstra"
                st.session_state.agent_stats['apstra_calls'] += 1
            elif is_configuration_message(clean_msg):
                agent_indicator = "🔧 Interface Config Assistant"
                if "✅" in clean_msg and "COMPLETE" in clean_msg:
                    st.session_state.agent_stats['interface_configs_completed'] += 1
            else:
                agent_indicator = "🏗️ MSO Triage"
            
            # Special styling for configuration messages
            message_class = "config-status" if is_configuration_message(clean_msg) else "assistant-message"
            
            st.markdown(f"""
            <div class="chat-message {message_class}">
                <strong>SANDMAN {agent_indicator}:</strong> {clean_msg}
                <br><small>{timestamp}</small>
            </div>
            """, unsafe_allow_html=True)
            
            # Display JSON configuration if present OR if it's a final JSON message
            final_json_from_message = None
            if is_final_json_message(clean_msg):
                final_json_from_message = extract_final_json_from_message(clean_msg)
                logger.info(f"Extracted final JSON from message: {final_json_from_message is not None}")
            
            display_json = json_config or final_json_from_message
            
            if display_json:
                col1, col2 = st.columns([3, 2])
                
                with col1:
                    expander_title = "🎉 Final Configuration" if final_json_from_message else "📋 View Generated Configuration"
                    with st.expander(expander_title, expanded=final_json_from_message is not None):
                        st.json(display_json)
                
                with col2:
                    # Generate appropriate filename
                    if final_json_from_message:
                        filename = generate_download_filename(final_json_from_message)
                        download_label = "📥 Download Final Config"
                        button_type = "primary"
                        st.markdown("### 🎯 Download Ready!")
                    else:
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"sandman_config_{timestamp_str}.json"
                        download_label = "📥 Download"
                        button_type = "secondary"
                    
                    # Convert JSON to pretty formatted string
                    json_str = json.dumps(display_json, indent=2)
                    
                    # Show filename before download button
                    st.info(f"📄 **Filename:** {filename}")
                    
                    st.download_button(
                        label=download_label,
                        data=json_str,
                        file_name=filename,
                        mime="application/json",
                        key=f"download_json_{i}_{timestamp}",
                        use_container_width=True,
                        type=button_type
                    )
                    
                    if final_json_from_message:
                        st.success("✅ Configuration Complete!")
                        # Show file info if auto-saved message is present
                        if "💾 Configuration automatically saved" in clean_msg:
                            st.success("💾 Also saved to payload/")
                            # Extract the saved filename from the message - look for the pattern after "saved to:"
                            saved_match = re.search(r'saved to:\s*(.+\.json)', clean_msg)
                            if saved_match:
                                saved_filename = saved_match.group(1).strip()
                                st.info(f"📁 **Payload file:** {saved_filename}")
                            else:
                                # Fallback: look for any .json filename in the message
                                json_file_match = re.search(r'([a-zA-Z0-9_]+\.json)', clean_msg)
                                if json_file_match:
                                    saved_filename = json_file_match.group(1)
                                    st.info(f"📁 **Payload file:** {saved_filename}")
                                else:
                                    st.info("📁 **Saved to payload directory**")
                        
                        # Add instructions
                        st.markdown("**Instructions:**")
                        st.markdown("1. Click the download button above")
                        st.markdown("2. File is also auto-saved to payload/ directory")
                        st.markdown("3. Ready for deployment!")
            
            # Special notification for final configuration
            if final_json_from_message:
                st.balloons()
                with st.container():
                    st.success("🎉 **EVPN VPWS Configuration Complete!** The final JSON is ready for deployment.")
                    st.markdown("---")


def add_to_chat_history(user_message, assistant_message, json_config=None):
    """Add messages to chat history"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_entry = {
        'timestamp': timestamp,
        'user_message': user_message,
        'assistant_message': assistant_message
    }
    
    if json_config:
        chat_entry['json_config'] = json_config
    
    st.session_state.chat_history.append(chat_entry)
    st.session_state.agent_stats['total_queries'] += 1


def display_session_management():
    """Display session management controls in sidebar"""
    st.sidebar.markdown("### 🧠 Session Memory")
    
    # Current session info
    session_summary = st.session_state.get('session_summary', {})
    st.sidebar.metric("Current Session Messages", session_summary.get('total_messages', 0))
    st.sidebar.metric("User Messages", session_summary.get('user_messages', 0))
    st.sidebar.metric("Assistant Messages", session_summary.get('assistant_messages', 0))
    
    # Session controls
    if st.sidebar.button("🗑️ Clear Session Memory"):
        try:
            success = run_async(
                st.session_state.sandman_client.clear_session_history(st.session_state.session_id)
            )
            if success:
                st.sidebar.success("Session memory cleared!")
                # Also clear local chat history
                st.session_state.chat_history = []
                st.session_state.session_summary = {}
            else:
                st.sidebar.error("Failed to clear session memory")
        except Exception as e:
            st.sidebar.error(f"Error clearing session: {e}")
    
    if st.sidebar.button("🔄 New Session"):
        # Generate new session ID
        new_session_id = f"session_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.session_id = new_session_id
        st.session_state.chat_history = []
        st.session_state.session_summary = {}
        st.sidebar.success("Started new session!")
        st.rerun()
    
    # Display session ID (truncated)
    st.sidebar.markdown(f"**Current Session:** `{st.session_state.session_id[:20]}...`")


def display_conversation_examples():
    """Display example conversations in sidebar"""
    st.sidebar.markdown("### 💡 Example Conversations")
    
    with st.sidebar.expander("EVPN VPWS Service", expanded=False):
        st.markdown("""
        **You:** "Create EVPN VPWS between Cambodia and Thailand sites"
        
        **SANDMAN:** *Generates base configuration*
        
        **SANDMAN:** "For site kh_site1, what interface type: tagged or untagged?"
        
        **You:** "tagged"
        
        **SANDMAN:** "For tagged interface: speed, LLDP, OAM?"
        
        **You:** "1000, yes, no"
        """)
    
    with st.sidebar.expander("Interface Configuration", expanded=False):
        st.markdown("""
        **Tagged Interface Example:**
        - Interface Type: "tagged"
        - Speed: "10000" (Mbps)
        - LLDP: true
        - OAM: false
        
        **Untagged Interface Example:**
        - Interface Type: "untagged"  
        - CVLAN ID: 200
        """)


def main():
    # Initialize session state
    initialize_session_state()
    
    # Display agent status
    display_agent_status()
    
    # Sidebar with information and session management
    with st.sidebar:
        st.markdown("### 🏗️ SANDMAN Agents")
        st.markdown("""
        **Routing Director Agent**
        - EVPN VPWS/ELAN Services
        - L3VPN Configuration
        - L2Circuit Management
        
        **Security Director Agent**
        - Security Policies
        - Firewall Rules
        - Access Control
        
        **Apstra Agent**
        - Data Center Fabric
        - Network Topology
        - Infrastructure Monitoring
        
        **Interface Config Assistant**
        - Conversational Interface Setup
        - Tagged/Untagged Configuration
        - Parameter Validation
        """)
        
        st.markdown("---")
        
        # Session management
        display_session_management()
        
        st.markdown("---")
        st.markdown("### 📊 Session Stats")
        stats = st.session_state.agent_stats
        st.metric("Total Queries", stats['total_queries'])
        st.metric("Routing Calls", stats['routing_director_calls'])
        st.metric("Security Calls", stats['security_director_calls'])
        st.metric("Apstra Calls", stats['apstra_calls'])
        st.metric("Interface Configs", stats['interface_configs_completed'])
        
        st.markdown("---")
        
        # Conversation examples
        display_conversation_examples()
    
    # Clear chat button
    col1, col2 = st.columns([4, 1])
    
    with col1:
        st.markdown("### 💬 Chat with SANDMAN Multi-Agent System")
    
    with col2:
        if st.button("🗑️ Clear Chat Display"):
            st.session_state.chat_history = []
            st.session_state.agent_stats = {
                'total_queries': 0,
                'routing_director_calls': 0,
                'security_director_calls': 0,
                'apstra_calls': 0,
                'interface_configs_completed': 0
            }
            st.success("Chat display cleared! (Session memory preserved)")
            st.rerun()
    
    # Chat area
    st.markdown("---")
    
    # Display chat history
    if st.session_state.chat_history:
        chat_container = st.container()
        with chat_container:
            display_chat_history()
    else:
        # Check if we have session memory even if local chat is empty
        session_summary = st.session_state.get('session_summary', {})
        if session_summary.get('total_messages', 0) > 0:
            st.info(f"🧠 **Session Memory Active** - I remember our previous {session_summary.get('total_messages', 0)} messages! What would you like to work on?")
        else:
            st.info("🏗️ Hello! I'm SANDMAN, your Multi-Agent Service Orchestrator with conversational interface configuration. I can help you create network services and configure interfaces through natural conversation. How can I help you today?")
    
    # Chat input
    st.markdown("---")
    
    # Chat input form
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        
        with col1:
            user_input = st.text_input(
                "Type your message:",
                placeholder="Create EVPN VPWS service, configure interfaces, or answer configuration questions...",
                label_visibility="collapsed"
            )
        
        with col2:
            send_button = st.form_submit_button("🚀 Send", use_container_width=True)
        
        if send_button and user_input:
            try:
                with st.spinner("🏗️ SANDMAN is processing your request..."):
                    # Send message with session ID for memory persistence
                    response = run_async(
                        st.session_state.sandman_client.send_message(
                            user_input, 
                            st.session_state.session_id
                        )
                    )
                    
                    # Try to extract JSON config if present
                    json_config = st.session_state.sandman_client.extract_json_from_response(response)
                    
                    # Add to local chat history for display
                    add_to_chat_history(user_input, response, json_config=json_config)
                    
                    # Update session summary
                    session_summary = run_async(
                        st.session_state.sandman_client.get_session_summary(st.session_state.session_id)
                    )
                    st.session_state.session_summary = session_summary
                    
                    # Rerun to update chat display
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Error: {str(e)}")
                logger.error(f"Error in main chat processing: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; font-size: 0.8rem;">
        🏗️ <strong>SANDMAN</strong> - Multi-Agent Service Orchestrator with Conversational Interface Configuration<br>
        <small>Persistent Session Memory • Multi-Agent Coordination • Conversational Service Configuration</small><br>
        <small>Powered by OpenAI Agents SDK • MCP Servers • Enhanced Interface Configuration Assistant</small>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()