import logging
import os, json, httpx
from dotenv import load_dotenv
from urllib.parse import urlencode
from openai import OpenAI
from typing import Dict, List, Any, Optional
from pathlib import Path
import pandas as pd
from ncclient import manager
import xml.etree.ElementTree as ET



from servicesConfigGenerator import ParagonAuth
from servicesConfigGenerator import serviceConfigGenerator
from servicesConfigGenerator import make_api_request_sync
from evpn_vpws_parser import parse_evpn_vpws_json
from l3vpn_parser import parse_l3vpn_json
from l2ckt_parser import parse_l2circuit_json
from evpn_elan_parser import parse_evpn_json

# Load environment variables
load_dotenv(override=True)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv('BASE_URL', "https://66.129.234.204:48800")
ORG_ID = os.getenv('ORG_ID', "0eaf8613-632d-41d2-8de4-c2d242325d7e")

# Initialize authentication
try:
    auth = ParagonAuth()
except ValueError as e:
    logger.error(f"Authentication initialization failed: {e}")
    auth = None


class utilityFunctions():
    @staticmethod
    async def make_api_request_sync(endpoint: str, method: str = "GET", payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make HTTP request to the API with authentication (synchronous version)"""
        if auth is None:
            return {"error": "Authentication not configured. Check .env file."}
        
        try:
            url = f"{BASE_URL}{endpoint}"
            logger.info("url ---> {}".format(url))
            
            headers = auth.get_headers(use_basic_auth=True)
            
            # Use httpx sync client instead of async
            with httpx.Client(verify=False, timeout=60.0) as client:
                if method == "GET":
                    response = client.get(url, headers=headers)
                elif method == "POST" or "DELETE":
                    if payload:
                        response = client.post(url, headers=headers, json=payload)
                    else:
                        response = client.post(url, headers=headers)
                else:
                    return {"error": f"Unsupported HTTP method: {method}"}
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                else:
                    return {"success": True, "message": "Request completed successfully"}
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Authentication failed - check username/password in .env")
                return {"error": "Authentication failed - invalid credentials"}
            elif e.response.status_code == 403:
                return {"error": "Access forbidden - insufficient permissions"}
            else:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return {"error": str(e)}

class APIEndpoint:
    """Class to represent API endpoint information"""
    def __init__(self, path: str, method: str, description: str, required_params: List[str] = None, optional_params: List[str] = None):
        self.path = path
        self.method = method
        self.description = description
        self.required_params = required_params or []
        self.optional_params = optional_params or []

ENDPOINTS = {
    "get_instances": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/instances",
        "GET",
        "Get all Service Instances for an Organization. Includes meta information and status from the latest Service Order per Service Instance. Use pagination for large datasets and filters to limit results.",
        required_params=["org_id"],
        optional_params=["per-page", "current-offset", "filter"]
    ),
    "get_orders": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/orders",
        "GET",
        "Get all service orders for an Organization including history. Contains multiple entries for same Service Instance if multiple orders were executed. Use pagination and filters to manage large datasets.",
        required_params=["org_id"],
        optional_params=["per-page", "current-offset", "filter"]
    ),
    "create_order": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order",
        "POST",
        "Create a new service order. Requires JSON payload with service configuration.",
        required_params=["org_id"],
        optional_params=[]
    ),
    "update_placements": APIEndpoint(
        "/api-aggregator/api/v1/orgs/{org_id}/aggregate/fhplace?customer_id={customer_id}&instance_id={instance_name}",
        "GET",
        "Update the resources/placements for a service or instance already uploaded in Routing Director",
        required_params=["org_id", "customer_id", "instance_name"],
        optional_params=[]
    ),
    "execute_order": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/customers/{customer_id}/instances/{instance_name}/exec",
        "POST",
        "Execute a created service order to provision the service.",
        required_params=["org_id", "customer_id", "instance_name"],
        optional_params=[]
    ),
    "get_instance": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/customers/{customer_id}/instances/{instance_name}",
        "GET",
        "Get detailed status and information for a specific service instance.",
        required_params=["org_id", "customer_id", "instance_id"],
        optional_params=[]
    ),
    "get_customers": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/customers",
        "GET",
        "Get all customers for an Organization with their customer IDs and details.",
        required_params=["org_id"],
        optional_params=[]
    ),
    "get_devices": APIEndpoint(
        #"/service-orchestration/api/v1/orgs/{org_id}/order/devices",
        "/trust/api/v1.1alpha/{org_id}/devices",
        "GET",
        "Get all devices for an Organization with their device IDs and details.",
        required_params=["org_id"],
        optional_params=[]
    ),
    "create_customer": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/customers",
        "POST",
        "Create a customer for an Organization. Requires JSON Payload with customer name",
        required_params=["org_id", "name"],
        optional_params=[]
    ),
    "delete_order": APIEndpoint(
        "/service-orchestration/api/v1/orgs/{org_id}/order/customers/{customer_id}/instances/{instance_id}/exec",
        "POST",
        "Delete a created ",
        required_params=["org_id", "customer_id", "instance_id"],
        optional_params=[]
    ),
}

class servicesManager():
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(current_dir, '.env')
        load_dotenv(dotenv_path=env_path, override=True)

    async def get_services(self, service_type:str):

        api_path = ENDPOINTS['get_instances'].path
        api_path = api_path.format(org_id=ORG_ID)
        logger.info(f"it's in service manager class {api_path}")
        all_services = await utilityFunctions.make_api_request_sync(api_path, method="GET")
        #logger.info(f"printing all services if it's successful {all_services}")
        if service_type == "all_services":
            return all_services
        elif service_type == "evpn_vpws":
            evpn_vpws_services = parse_evpn_vpws_json(all_services)
            return evpn_vpws_services
        elif service_type == "evpn_elan":
            evpn_elan_services = parse_evpn_json(all_services)
            return evpn_elan_services
        elif service_type == "l2circuit":
            l2circuit_services = parse_l2circuit_json(all_services)
            return l2circuit_services
        elif service_type == "l3vpn":
            l3vpn_services = parse_l3vpn_json(all_services)
            return l3vpn_services
        else:
            print(f"Service Type selected by LLM AGENT {service_type} is wrong.!!!")
        return []
    
    async def get_service(self, instance_name:str, return_customer_id: bool=False):
        api_path = ENDPOINTS['get_instance'].path
        customer_id, instance_id = await self.get_cust_id_and_inst_id_by_inst_name(instance_name=instance_name)
        api_path = api_path.format(org_id=ORG_ID, customer_id=customer_id, instance_name=instance_name)
        svc_to_delete = await utilityFunctions.make_api_request_sync(api_path, method="GET")
        if return_customer_id == True:
            return svc_to_delete, customer_id
        else:
            return svc_to_delete
        

    async def delete_service(self, instance_name:str, return_customer_id: bool):
        logger.info(f"I am in servicesAgent delete service {instance_name}")
        svc_to_delete, customer_id = await self.get_service(instance_name=instance_name, return_customer_id=return_customer_id)
        svc_to_delete = svc_to_delete[0]
        svc_to_delete['operation'] = "delete"
        print(f"{svc_to_delete}")

        api_path = ENDPOINTS['create_order'].path
        api_path = api_path.format(org_id=ORG_ID)
        delete_order = await utilityFunctions.make_api_request_sync(api_path, method="POST", json_data=svc_to_delete)

        api_path = ENDPOINTS['execute_order'].path
        api_path = api_path.format(org_id=ORG_ID, customer_id=customer_id, instance_name=instance_name)
        svc_deleted = await utilityFunctions.make_api_request_sync(api_path, method="POST", json_data=svc_to_delete)
        print(f"svc_deleted json {svc_deleted}")

        return svc_deleted
    
    async def create_service(self, service_type:str, customer_name: str, hostnames:list):
        logger.info(f"****** I am in create service in services agent {service_type}, {customer_name}, {hostnames}")
        logger.info(f"****** create service triggered")
        
        try:
            logger.info(f"****** About to create serviceConfigGenerator instance")
            scg = serviceConfigGenerator()
            logger.info(f"****** serviceConfigGenerator instance created successfully")
            
            logger.info(f"****** About to call fill_fields")
            result = scg.fill_fields(service_type=service_type, customer_name=customer_name, hostnames=hostnames)
            logger.info(f"****** Filled json in create_service serviceAgent.py {result}")
            return result
            
        except Exception as e:
            logger.error(f"****** Exception in create_service: {str(e)}")
            logger.error(f"****** Exception type: {type(e)}")
            import traceback
            logger.error(f"****** Full traceback: {traceback.format_exc()}")
            raise e
    
    async def create_customer(self, customer_name: str, customer_ref_no: Optional[str], 
                               customer_description: Optional[str]):
        logger.info(f"****** I am trying to create customer")
        api_path = ENDPOINTS['create_customer'].path
        method = ENDPOINTS['create_customer'].method
        api_path = api_path.format(org_id=ORG_ID)

        payload = {"name":customer_name, "reference_number": customer_ref_no if customer_ref_no else "", 
                   "description": customer_description if customer_description else ""}

        cust_create = await utilityFunctions.make_api_request_sync(api_path, method=method, payload=payload)

        if "error" in cust_create:
            return f"Customer {customer_name} creation Failed"
        else:
            return f"Customer {customer_name} created Successfully"
        
    async def upload_service(self, json_filename: str):
        logger.info(f"****** I am trying to upload service from file: {json_filename}")
        
        try:
            # Construct the full path to the JSON file in payload directory
            payload_dir = Path("payload")
            file_path = payload_dir / json_filename
            
            # Check if file exists
            if not file_path.exists():
                logger.error(f"File {json_filename} not found in payload directory")
                return f"Error: File {json_filename} not found in payload directory"
            
            # Read and load JSON content from file
            with open(file_path, 'r') as f:
                payload = json.load(f)
            
            logger.info(f"Successfully loaded JSON payload from {json_filename}")
            
            # Extract instance name for logging/response
            instance_name = payload.get('instance_id', 'Unknown')
            
            # API configuration
            api_path = ENDPOINTS['create_order'].path
            method = ENDPOINTS['create_order'].method
            api_path = api_path.format(org_id=ORG_ID)
            
            # Make API request with loaded payload
            svc_to_upload = await utilityFunctions.make_api_request_sync(api_path, method=method, payload=payload)

            if "error" in svc_to_upload:
                error_msg = svc_to_upload.get('error', 'Unknown error')
                logger.error(f"Service upload failed: {error_msg}")
                return f"Service {instance_name} Upload Failed: {error_msg}"
            else:
                logger.info(f"Service {instance_name} uploaded successfully")
                return f"Service {instance_name} Uploaded Successfully"
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {json_filename}: {e}")
            return f"Error: Invalid JSON format in file {json_filename}"
        except Exception as e:
            logger.error(f"Error uploading service from {json_filename}: {e}")
            return f"Error uploading service: {str(e)}"
        
    async def update_placements(self, instance_name:str):
        api_path = ENDPOINTS['update_placements'].path
        method = ENDPOINTS['update_placements'].method
        customer_id, instance_id = await self.get_cust_id_and_inst_id_by_inst_name(instance_name=instance_name)
        api_path = api_path.format(org_id=ORG_ID, customer_id=customer_id, instance_name=instance_name)
        svc_to_validate = await utilityFunctions.make_api_request_sync(api_path, method=method)
        if "error" in svc_to_validate:
            return f"Resource Validation for Service {instance_name} Failed"
        else:
            return "Resource Validation/Update Placements for Service {instance_name} is successful"
    
    async def deploy_service(self, instance_name:str):
        api_path = ENDPOINTS['execute_order'].path
        method = ENDPOINTS['execute_order'].method
        customer_id, instance_id = await self.get_cust_id_and_inst_id_by_inst_name(instance_name=instance_name)
        api_path = api_path.format(org_id=ORG_ID, customer_id=customer_id, instance_name=instance_name)
        svc_to_deploy = await utilityFunctions.make_api_request_sync(api_path, method=method)

        if "error" in svc_to_deploy:
            return f"Service {instance_name} deployment failed"
        else:
            return f"Service {instance_name} deployed successfully"

    
    async def get_cust_id_and_inst_id_by_inst_name(self, instance_name:str):
        all_services = await self.get_services("all_services")
        return next(
            (
                [instance['customer_id'], instance['instance_id']]
                for instance in all_services
                if instance['instance_id'] == instance_name
            ), 
            "Provide Instance Name is not available"
        )
    
    async def discover_l2vpn_bgp_signaling_services(router_list_filepath: str, output_filepath: str, 
                          username: str = 'jcluser', password: str = 'Juniper!1',
                          host: str = '66.129.234.204'):
        """
        Discover L2VPN bgp signaling services from Juniper routers and save to Excel
        
        Args:
            router_list_filepath: Path to Excel file containing router list with 'Port' column
            output_filepath: Path for output Excel file
            username: SSH username (default: 'jcluser')
            password: SSH password (default: 'Juniper!1')
            host: SSH host IP (default: '66.129.234.204')
            
        Returns:
            dict: Summary of discovery results
        """
        
        # Validate input file exists
        if not Path(router_list_filepath).exists():
            raise FileNotFoundError(f"Router list file not found: {router_list_filepath}")
        
        # Load Excel file with IP addresses
        try:
            df = pd.read_excel(router_list_filepath, engine='openpyxl')
            if 'Port' not in df.columns:
                raise ValueError("Excel file must contain 'Port' column")
        except Exception as e:
            raise Exception(f"Error reading router list file: {str(e)}")

        hardware_data = []
        l2vpn_data = []
        successful_connections = 0
        failed_connections = 0
        connection_errors = []

        print(f"Starting discovery for {len(df)} routers...")
        
        for index, row in df.iterrows():
            sshport = row['Port']
            print(f"\nConnecting to {host} port:{sshport}... ({index+1}/{len(df)})")
            
            try:
                with manager.connect(
                    host=host,
                    port=sshport,
                    username=username,
                    password=password,
                    hostkey_verify=False,
                    device_params={'name': 'junos'},
                    allow_agent=False,
                    look_for_keys=False
                ) as m:

                    # --- Hardware Info ---
                    version_reply = m.command('show version | display xml', format='xml')
                    version_root = ET.fromstring(str(version_reply))

                    hostname = version_root.findtext('.//host-name')
                    product_model = version_root.findtext('.//product-model')
                    junos_version = version_root.findtext('.//junos-version')

                    interface_reply = m.command('show configuration interfaces lo0.0 family inet |display xml', format='xml')
                    interface_root = ET.fromstring(str(interface_reply))

                    lo0_ip = None
                    for af in interface_root.findall('.//family'):
                        af_name = af.findtext('address')
                        lo0_ip = af.findtext('.//name')
                        break

                    hardware_data.append({
                        'hostname': hostname,
                        'product-model': product_model,
                        'junos-version': junos_version,
                        'lo0.0 inet ip': lo0_ip
                    })
                    print(f' ### Lo0 IP = {lo0_ip} ###')
                    print("####### Finish Extract Hardware Info ######")

                    # --- L2VPN Info ---
                    l2vpn_reply = m.command('show l2vpn connection | display xml', format='xml')
                    l2vpn_root = ET.fromstring(str(l2vpn_reply))

                    for conn in l2vpn_root.findall('.//instance'):
                        instance_name = conn.findtext('.//instance-name')
                        local_site = conn.findtext('.//local-site-id')

                        for rpe in conn.findall('.//connection'):
                            remote_pe = rpe.findtext('remote-pe')
                            conn_status = rpe.findtext('connection-status')
                            interface_name = rpe.findtext('.//local-interface/interface-name')
                            interface_status = rpe.findtext('.//local-interface/interface-status')

                            entry = {
                                'hostname': hostname,
                                'instance-name': instance_name,
                                'Instance Type': None,
                                'local-site': local_site,
                                'connection-status': conn_status,
                                'remote-pe': remote_pe,
                                'interface-name': interface_name,
                                'interface id': None,
                                'unit id': None,
                                'IFD description': None,
                                'Unit Description': None,
                                'interface-status': interface_status,
                                'Route Target': None,
                                'outer-vlan': None,
                                'inner-vlan': None   
                            }

                            # --- VLAN Parsing ---
                            print("####### Start VLAN PARSING #########")
                            try:
                                if conn_status == "Up":
                                    ifd, unit_id = interface_name.split('.')
                                    entry['interface id'] = ifd
                                    entry['unit id'] = unit_id
                                    config_reply = m.command('show configuration interfaces | display xml |display inheritance no-comments', format='xml')
                                    config_root = ET.fromstring(str(config_reply))

                                    for iface in config_root.findall('.//interface'):
                                        name = iface.findtext('name')
                                        if name == ifd:
                                            desc = iface.findtext('description')
                                            print(f"IFD Description = {desc}")
                                            entry['IFD description'] = desc
                                            for unit in iface.findall('.//unit'):
                                                unit_name = unit.findtext('name')
                                                if unit_name == unit_id:
                                                    unit_desc = unit.findtext('description')
                                                    print(f'Unit: {unit_name} description is {unit_desc}')
                                                    entry['Unit Description'] = unit_desc
                                                    vlan_tags = unit.find('.//vlan-tags')
                                                    vlan_id = unit.findtext('.//vlan-id')

                                                    if vlan_tags is not None:
                                                        outer = vlan_tags.findtext('outer')
                                                        inner = vlan_tags.findtext('inner')
                                                        if outer and inner:
                                                            entry['outer-vlan'] = outer
                                                            entry['inner-vlan'] = inner
                                                        elif outer and not inner:
                                                            entry['outer-vlan'] = outer
                                                            entry['inner-vlan'] = '0'
                                                        else:
                                                            entry['outer-vlan'] = entry['inner-vlan'] = 'config error'
                                                    elif vlan_id:
                                                        entry['outer-vlan'] = vlan_id
                                                        entry['inner-vlan'] = '0'
                                                    else:
                                                        entry['outer-vlan'] = entry['inner-vlan'] = '0'
                                else:
                                    entry['outer-vlan'] = 'None'
                                    entry['inner-vlan'] = 'None'

                            except Exception as e:
                                print(f"Error parsing VLAN config for {interface_name}: {e}")
                                entry['outer-vlan'] = entry['inner-vlan'] = 'parse error'

                            l2vpn_data.append(entry)

                    # --- Routing Instances for Route Target ---
                    routing_reply = m.command('show configuration routing-instances | display xml |display inheritance no-comments', format='xml')
                    routing_root = ET.fromstring(str(routing_reply))

                    for instance in routing_root.findall('.//instance'):
                        name = instance.findtext('name')
                        community = instance.findtext('.//community')
                        instance_type = instance.findtext('instance-type')
                        print(f'### Instance type = {instance_type} ###')
                        for entry in l2vpn_data:
                            if entry['hostname'] == hostname and entry['instance-name'] == name:
                                entry['Route Target'] = community
                                entry['Instance Type'] = instance_type

                    successful_connections += 1
                    print(f"✅ Successfully processed {hostname}")

            except Exception as e:
                failed_connections += 1
                error_msg = f"Failed to connect to {host}:{sshport}: {e}"
                print(error_msg)
                connection_errors.append(error_msg)

        # Save to Excel
        try:
            # Create output directory if it doesn't exist
            output_path = Path(output_filepath)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with pd.ExcelWriter(output_filepath, engine='openpyxl') as writer:
                pd.DataFrame(hardware_data).to_excel(writer, sheet_name='Hardware', index=False)
                pd.DataFrame(l2vpn_data).to_excel(writer, sheet_name='L2VPN', index=False)

            print(f"\n✅ Data has been written to {output_filepath}")
            
        except Exception as e:
            raise Exception(f"Error writing output file: {str(e)}")

        # Return summary
        summary = {
            'total_routers': len(df),
            'successful_connections': successful_connections,
            'failed_connections': failed_connections,
            'hardware_records': len(hardware_data),
            'l2vpn_records': len(l2vpn_data),
            'output_file': output_filepath,
            'connection_errors': connection_errors
        }
        
        return summary

if __name__ == "__main__":
    # Setup Logging Configs
    logging.basicConfig(level=logging.INFO)

    try:
        sm = servicesManager()
        a = sm.delete_service(instance_name='l2ckt1')
    
    except ValueError as e:
        print(f"Failed to initialize generator: {e}")
        logger.info(f"Failed to initialize generator: {e}")
