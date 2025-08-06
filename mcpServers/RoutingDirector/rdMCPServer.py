import logging
import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from servicesAgent import servicesManager
from typing import Optional

mcp = FastMCP("Routing_Director_MCP_Server")
logger = logging.getLogger(__name__)

async def save_completed_json(json_data: Dict, service_type: str, hostnames: list) -> str:
    """Save completed JSON to payload directory with specified filename format"""
    try:
        # Create payload directory if it doesn't exist
        payload_dir = Path("payload")
        payload_dir.mkdir(exist_ok=True)
        
        # Generate filename: <service_type>_<hostname1>_<hostname2>_timestamp.json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname1 = hostnames[0] if len(hostnames) > 0 else "unknown"
        hostname2 = hostnames[1] if len(hostnames) > 1 else "unknown"
        
        filename = f"{service_type}_{hostname1}_{hostname2}_{timestamp}.json"
        file_path = payload_dir / filename
        
        # Save JSON with pretty formatting
        with open(file_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        logger.info(f"Saved completed JSON to: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error saving JSON: {e}")
        return f"Error saving JSON: {str(e)}"

@mcp.tool()
async def get_specific_service_details(instance_name: str):
    """Get the specific only one single Service/Instance details

    Args:
        instance name: The name of the service/instance already provisioned 
        to fetch details
    """
    
    svc_mgr = servicesManager()
    return await svc_mgr.get_service(instance_name=instance_name)

@mcp.tool()
async def delete_service(instance_name: str):
    """Delete the service/instance provisioned

    Args:
        instance name: The name of the service/instance already provisioned 
        required to be deleted
    """
    svc_mgr = servicesManager()
    logger.info(f"I am in mcp server delete_service {instance_name}")
    return await svc_mgr.delete_service(instance_name=instance_name, return_customer_id=True)

@mcp.tool()
async def get_services(service_type):
    """1. If User asks to get/fetch all services Or \n
    2. asks to fetch all services of evpn_elan services Or \n
    3. asks to fetch all evpn_vpws services Or \n
    4. asks to fetch all l3vpn services Or \n
    5. asks to fetch all l2circuits services \n

    Args:
        service_type:  service type is needed. Only these 5 values are allowed - 
        "evpn_elan", "evpn_vpws", "l3vpn", "l2circuit", "all_services"
    """
    svc_mgr = servicesManager()
    return await svc_mgr.get_services(service_type=service_type)

@mcp.tool()
async def create_service(service_type: str, customer_name: str, hostnames: list):
    """Create the service/instance. Currently only evpn vpws service provisioning is supported

    Args:
        service_type:  service type is needed. Only these 5 values are allowed - 
        "evpn_elan", "evpn_vpws", "l3vpn", "l2circuit"
        
        customer_name: customer name for whom the service needs to be created
        
        hostnames: This is a list, it includes both source hostname and destination hostname. 
        Minimum this variable should contain two hostnames.
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.create_service(service_type=service_type, customer_name=customer_name, hostnames=hostnames)
    logger.info(f"****** mcp tool result: {result}")
    
    # Return the structured result that includes missing field information
    return result

@mcp.tool()
async def create_customer(customer_name: str, customer_ref_no: Optional[str], 
                           customer_description: Optional[str]):
    """Create a customer or set of customers in routing director

    Args:
        customer_name: This is a customer name that user wants to create
        
        customer_ref_no: This is customer reference number to identify customer by reference number, 
        provided by user, if not available then fill it with ""

        customer_description: This is description for each customer provided by user, 
        if not available then fill it with ""
        
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.create_customer(customer_name=customer_name, customer_ref_no=customer_ref_no, 
                                            customer_description=customer_description)
    logger.info(f"****** mcp tool result: {result}")
    
    # Return the structured result that includes missing field information
    return result


@mcp.tool()
async def create_jsonbody_for_service(service_type: str, customer_name: str, hostnames: list):
    """Create/Generate the json body required to create service/instance. 
    Currently only evpn vpws service provisioning is supported

    Args:
        service_type:  service type is needed. Only these 5 values are allowed - 
        "evpn_elan", "evpn_vpws", "l3vpn", "l2circuit"
        
        customer_name: customer name for whom the service needs to be created
        
        hostnames: This is a list, it includes both source hostname and destination hostname. 
        Minimum this variable should contain two hostnames.
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.create_service(service_type=service_type, customer_name=customer_name, hostnames=hostnames)
    logger.info(f"****** mcp tool result: {result}")

    return result

@mcp.tool()
async def upload_service_to_RD(json_filename: str):
    """Uploads the service into Routing Director. This tool requires json body to upload a service/instance into RD.

    Args:
        payload: Payload is a json data that used to upload the service into RD.
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.upload_service(json_filename=json_filename)
    return result

@mcp.tool()
async def validate_resources(instance_name: str):
    """Validates the resources for the service already uploaded/available in routing director. 
    Sometimes validate resources is also called as update placements.

    Args:
        instance_name: instance name is the service name with which service to be validated
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.update_placements(instance_name=instance_name)
    return result

@mcp.tool()
async def deploy_service(instance_name: str):
    """Deploy the service which is already uploaded, validated with resources

    Args:
        instance_name: instance name is the service name with which service to be deployed
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.deploy_service(instance_name=instance_name)
    return result

@mcp.tool()
async def discover_brownfield_l2vpn_bgp_signaling_services(router_list_filepath: str, output_filepath: str, 
                          username: str = 'jcluser', password: str = 'Juniper!1',
                          host: str = '66.129.234.204'):
    """This MCP Tool discovers the brownfield l2vpn bgp signaling services in devices

    Args:
        router_list_filepath: This is filepath for routers details

        output_filepath: This is the output filename that user wants to write discovered services into xlsx file

        username: This is username to access each network device from router_list_filepath xlsx

        password: This is password to access each network device

        host: This is the host IP to access devices
    """
    svc_mgr = servicesManager()
    result = await svc_mgr.discover_l2vpn_bgp_signaling_services(router_list_filepath=router_list_filepath,
                                                                 output_filepath=output_filepath,
                                                                 username=username, password=password,
                                                                 host=host)
    return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport='stdio')