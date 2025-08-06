import re, sys
import os
import json
import uuid
import copy
import httpx
import base64
import random
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Callable
from urllib.parse import urlencode
from helper_fns import clean_string

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('BASE_URL', "https://66.129.234.204:48800")
ORG_ID = os.getenv('ORG_ID', "0eaf8613-632d-41d2-8de4-c2d242325d7e")

class ParagonAuth:
    """Handle authentication for Routing Director"""
    
    def __init__(self):
        self.username = os.getenv('USERNAME')
        self.password = os.getenv('PASSWORD')
        self.token = None
        self.token_expiry = None
        
        if not self.username or not self.password:
            logger.error("USERNAME and PASSWORD must be set in .env file")
            raise ValueError("Missing credentials in .env file")
        
        logger.info(f"Authentication configured for user: {self.username}")
    
    def get_basic_auth_header(self) -> str:
        """Generate Basic Authentication header"""
        if not self.username or not self.password:
            raise ValueError("Username and password are required for authentication")
        
        credentials = f"{self.username}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"

    def get_auth_token(self) -> Optional[str]:
        """Get authentication token from API (if token-based auth is used)"""
        try:
            auth_url = f"{BASE_URL}/active-assurance/api/v2/auth/token"
            
            auth_payload = {
                "username": self.username,
                "password": self.password
            }
            
            with httpx.Client(verify=False, timeout=30.0) as client:
                response = client.post(
                    auth_url,
                    json=auth_payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    self.token = token_data.get('access_token')
                    logger.info("Token authentication successful")
                    return self.token
                else:
                    logger.error(f"Token authentication failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Token authentication error: {e}")
            return None
    
    def get_headers(self, use_basic_auth: bool = True) -> Dict[str, str]:
        """Get headers with authentication"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if use_basic_auth:
            # Use Basic Authentication
            headers["Authorization"] = self.get_basic_auth_header()
        elif self.token:
            # Use Bearer token if available
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers

# Initialize authentication
try:
    auth = ParagonAuth()
except ValueError as e:
    logger.error(f"Authentication initialization failed: {e}")
    auth = None

def make_api_request_sync(endpoint: str, method: str = "GET", json_data: Dict[str, Any] = None) -> Dict[str, Any]:
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
                if json_data:
                    response = client.post(url, headers=headers, json=json_data)
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


class utilityFunctions():
    @staticmethod
    def _replace_in_dict(obj: Any, replacements: Dict[str, str]) -> Any:
        """Recursively replace placeholders in dictionary/list structures"""
        if isinstance(obj, dict):
            return {key: utilityFunctions._replace_in_dict(obj=value, replacements=replacements) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [utilityFunctions._replace_in_dict(obj=item, replacements=replacements) for item in obj]
        elif isinstance(obj, str):
            result = obj
            for placeholder, value in replacements.items():
                result = result.replace(placeholder, value)
            return result
        else:
            return obj

class serviceConfigGenerator():
    """Generate service configuration JSON bodies using OpenAI for parsing and JUNOS config generation"""

    def __init__(self, form_handler: Optional[Callable] = None):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(current_dir, '.env')
        load_dotenv(dotenv_path=env_path, override=True)

        # Store form handler callback for GUI communication
        self.form_handler = form_handler

        #Get Updated Customers & Devices Data from Routing Director
        CUSTOMER_API_ENDPOINT = os.getenv('CUSTOMERS_API_ENDPOINT')
        DEVICE_API_ENDPOINT = os.getenv('DEVICES_API_ENDPOINT')
        SITES_API_ENDPOINT = os.getenv('SITES_API_ENDPOINT')
        TOPO_API_ENDPOINT = os.getenv('TOPO_API_ENDPOINT')
        TOPO_FILE_NAME = os.getenv('TOPO_FILE_NAME')
        RD_RT_RESOURCES = os.getenv('RD_RT_RESOURCES')
        
        #Get customers Data
        api_path = CUSTOMER_API_ENDPOINT.format(org_id=ORG_ID)
        self.rd_customers_data = make_api_request_sync(api_path, method="GET")

        #Get Devices Data
        api_path = DEVICE_API_ENDPOINT.format(org_id=ORG_ID)
        self.rd_devices_data = make_api_request_sync(api_path, method="GET")

        #Get Site Details Data
        api_path = SITES_API_ENDPOINT.format(org_id=ORG_ID)
        self.site_details = make_api_request_sync(api_path, method="GET")

        #Get Topo Details Data
        self.infra_id = self.get_customer_id('network-operator')
        api_path = TOPO_API_ENDPOINT.format(org_id=ORG_ID, infra_id=self.infra_id, topo_file_name=TOPO_FILE_NAME)
        self.topo_details = make_api_request_sync(api_path, method="GET")

        #Get RD RT Resource Details Data
        api_path = TOPO_API_ENDPOINT.format(org_id=ORG_ID, infra_id=self.infra_id, topo_file_name=RD_RT_RESOURCES)
        self.rd_rt_details = make_api_request_sync(api_path, method="GET")

        self.service_designs = {
            "l2circuit": {
                "design_id": "eline-l2circuit-nsm",
            },
            "evpn_vpws": {
                "design_id": "eline-evpn-vpws-csm",
            }
        }

        self.services_dir = Path("services")
        self.services_dir.mkdir(exist_ok=True)
        logger.info(f"Services directory created/verified: {self.services_dir}")

        # Template file paths
        self.template_files = {
            "l2circuit": "services/l2circuit_template.json",
            "evpn_vpws": "services/evpn_vpws_template.json"
        }

    def _generate_evpn_vpws_json(self, service_type: str, customer_name: str, hostnames: list):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_filepath = os.path.join(current_dir, self.template_files[service_type])

        with open(template_filepath, 'r') as f:
            template = json.load(f)
        filled_template = copy.deepcopy(template)

        #Fetch Customer ID
        customer_id = self.get_customer_id(customer_name)
        
        #generate some random values for globla fields
        design_identifier = self.service_designs[service_type]["design_id"]
        instance_identifier = f"{service_type}_{random.randint(10000, 99999)}"
        clean_instance_identifier = clean_string(input_string=instance_identifier)
        logger.info(f"###### {clean_instance_identifier}")
        instance_uuid = str(uuid.uuid4())

        filled_template = utilityFunctions._replace_in_dict(obj=filled_template, replacements={
            "{CUSTOMER_UUID}": customer_id,
            "{DESIGN_IDENTIFIER}": design_identifier,
            "{INSTANCE_IDENTIFIER}": clean_instance_identifier,
            "{INSTANCE_UUID}": instance_uuid
        })

        logger.info(f"###### {filled_template}")

        base_site = filled_template['l2vpn_svc']['sites']['site'][0]
        filled_template['l2vpn_svc']['sites']['site'] = []

        #Find how many nodes in this service
        n_nodes = len(hostnames)
        logger.info(f"Total {n_nodes} nodes in this service")
        
        for i, v in enumerate(hostnames):
            device_id, site_id = self.get_device_and_site_ids(v)
            setattr(self, f"h{i}_device_id", device_id)
            setattr(self, f"h{i}_site_id", site_id)
            site_id = getattr(self, f"h{i}_site_id")
            site_country_code = self.get_site_details(site_id)['country_code']
            site_name = self.get_site_details(site_id)['name']
            setattr(self, f"h{i}_site_cc", site_id)

            #Site Creation
            new_site = copy.deepcopy(base_site)
            
            #Create Counters for Country (Sites) and Links
            cc_site_counter = defaultdict(int)
            country_count = cc_site_counter[site_country_code]+1

            cc_link_counter = defaultdict(int)
            link_count = cc_link_counter[f"{site_country_code.lower()}_link"]+1

            pop_name = f"{site_country_code.lower()}_site{country_count}"
            cc_site_counter[site_country_code] +=1

            new_site['site_network_accesses']['site_network_access'][0]['network_access_id'] = f"{site_country_code.lower()}_link{link_count}"
            cc_link_counter[f"{site_country_code.lower()}_link"] +=1

            postal_code = self.get_postal_code(infra_id=self.infra_id, site_id=site_id, country_code=site_country_code, site_name=site_name)

            new_site['site_id'] = pop_name
            if new_site['locations']['location']:
                new_site['locations']['location'][0]['country_code'] = site_country_code
                new_site['locations']['location'][0]['postal_code'] = postal_code
                new_site['locations']['location'][0]['location_id'] = pop_name

            filled_template['l2vpn_svc']['sites']['site'].append(new_site)

        return filled_template

    def _check_missing_fields(self, json_data: Dict) -> Tuple[bool, List[str]]:
        """Check for missing placeholder fields in the JSON configuration"""
        missing_fields = []
        
        def find_placeholders(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    find_placeholders(value, current_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    current_path = f"{path}[{i}]"
                    find_placeholders(item, current_path)
            elif isinstance(obj, str) and obj.startswith("{") and obj.endswith("}"):
                missing_fields.append((path, obj))
        
        find_placeholders(json_data)
        return len(missing_fields) > 0, missing_fields

    def _collect_form_data_for_sites(self, sites: List[Dict]) -> Dict[str, Any]:
        """Collect form data for each site and network access"""
        if not self.form_handler:
            logger.error("No form handler available for user input collection")
            return {}
        
        # Prepare form metadata
        form_metadata = {
            "service_type": "evpn_vpws",
            "sites_count": len(sites),
            "sites": []
        }
        
        for i, site in enumerate(sites):
            site_info = {
                "site_index": i,
                "site_id": site['site_id'],
                "country_code": site['locations']['location'][0]['country_code'],
                "network_accesses": []
            }
            
            for j, access in enumerate(site['site_network_accesses']['site_network_access']):
                access_info = {
                    "access_index": j,
                    "network_access_id": access['network_access_id'],
                    "required_fields": [
                        "eth_inf_type",
                        "cvlan_id",  # for tagged
                        "speed",     # for untagged
                        "lldp",      # for untagged
                        "oam_enabled"  # for untagged
                    ]
                }
                site_info["network_accesses"].append(access_info)
            
            form_metadata["sites"].append(site_info)
        
        # Call form handler to collect user input
        logger.info(f"Requesting form data from GUI for {len(sites)} sites")
        try:
            form_data = self.form_handler(form_metadata)
            logger.info(f"Received form data: {form_data}")
            return form_data
        except Exception as e:
            logger.error(f"Error collecting form data: {e}")
            return {}

    def _complete_json_with_form_data(self, json_data: Dict, form_data: Dict[str, Any]) -> Dict:
        """Complete the JSON configuration with form data"""
        if not form_data:
            logger.warning("No form data provided, returning original JSON")
            return json_data
        
        completed_json = copy.deepcopy(json_data)
        sites = completed_json['l2vpn_svc']['sites']['site']
        
        for i, site in enumerate(sites):
            for j, access in enumerate(site['site_network_accesses']['site_network_access']):
                key_prefix = f"site_{i}_access_{j}"
                connection = access['connection']
                
                # Get form data for this site/access combination
                eth_inf_type = form_data.get(f"{key_prefix}_eth_intf_type", "untagged")
                
                # Update ethernet interface type
                connection['eth_inf_type'] = eth_inf_type
                
                if eth_inf_type == "tagged":
                    # Configure tagged interface
                    cvlan_id = form_data.get(f"{key_prefix}_cvlan_id", "100")
                    connection['tagged_interface']['dot1q_vlan_tagged']['cvlan_id'] = cvlan_id
                    
                    # Remove untagged interface configuration
                    if 'untagged_interface' in connection:
                        del connection['untagged_interface']
                        
                else:  # untagged
                    # Configure untagged interface
                    speed = form_data.get(f"{key_prefix}_speed", "10000")
                    lldp = form_data.get(f"{key_prefix}_lldp", True)
                    oam_enabled = form_data.get(f"{key_prefix}_oam", False)
                    
                    connection['untagged_interface']['speed'] = speed
                    connection['untagged_interface']['lldp'] = str(lldp).lower()
                    connection['untagged_interface']['oam_802.3ah_link']['enabled'] = str(oam_enabled).lower()
                    
                    # Remove tagged interface configuration
                    if 'tagged_interface' in connection:
                        del connection['tagged_interface']
        
        logger.info("JSON configuration completed with form data")
        return completed_json
    
    def fill_fields(self, service_type: str, customer_name: str, hostnames: list):
        """Fill template with generated values and handle user form interaction"""
        logger.info(f"****** fill_fields called in servicesConfigGenerator.py")
        
        if service_type == "evpn_vpws":
            # Generate initial JSON with placeholders
            default_json = self._generate_evpn_vpws_json(service_type=service_type, customer_name=customer_name, hostnames=hostnames)
            
            # Check for missing fields
            has_missing_fields, missing_field_list = self._check_missing_fields(default_json)
            
            if has_missing_fields and self.form_handler:
                logger.info(f"Missing fields detected: {len(missing_field_list)} placeholders found")
                
                # Extract sites for form handling
                sites = default_json['l2vpn_svc']['sites']['site']
                
                # Collect form data from user via GUI
                form_data = self._collect_form_data_for_sites(sites)
                
                if form_data:
                    # Complete JSON with form data
                    completed_json = self._complete_json_with_form_data(default_json, form_data)
                    logger.info("JSON configuration completed successfully")
                    return completed_json
                else:
                    logger.warning("No form data received, returning incomplete JSON")
                    return default_json
            else:
                logger.info("No missing fields detected or no form handler available")
                return default_json
                
        elif service_type == "l2circuit":
            return []

    def get_customer_id(self, customer_name: str):
        """ Get Customer ID from Routing Director 
        Input: Customer Name
        Output: Customer ID in string format 
        """
        return next(
            (
                customer["customer_id"]
                for customer in self.rd_customers_data
                if customer.get("name", "").lower() == customer_name.lower()
            ),
            None
        )

    def get_device_and_site_ids(self, device_name: str):
        """ Get Device ID & Site ID from Routing Director 
        Input: DeviceName/Hostname
        Output: [DeviceID, SiteID] in list format
        """
        return next(
            (
                [device.get("id"), device.get("siteId")]
                for device in self.rd_devices_data['devices']
                if device.get('hostname', "").lower() == device_name.lower()
            ),
            None
        )
    
    def get_site_details(self, site_id: str):
        """ Get Site Details of Routing Director 
        Input:  Site ID (User can send the Site ID created in Routing Director) (OR)
                If we user provides the device hostname, Site ID can be fetched by 
                calling funtion "get_device_and_site_ids" with device hostname as argument.
                The function get_device_and_site_ids gives back [Device id, Site ID] as list as output 
        Output: 
        """
        return next(
            (
                site
                for site in self.site_details
                if site.get("id", "").lower() == site_id.lower()
            ),
            None
        )
    
    def get_postal_code(self, infra_id: str, site_id: str, country_code: str, site_name: str):
        location_data = self.topo_details.get('resource', {}).get('location', {})['customer_id'][infra_id]
        if site_id in location_data['instance_id'][os.getenv('TOPO_FILE_NAME')]['pop'].keys():
            location_properties = location_data['instance_id'][os.getenv('TOPO_FILE_NAME')]['pop'][site_id]['numbered']['properties']
        else:
            return "Provided Site ID is not available in TOPO Resource File for Postal Code"
        return next(
            (
                p['regex']
                for p in location_properties['postal_code_matches']
                if p['country_code'] == country_code and p['name'] == site_name
            ), 
            "Country Code and Site name is not matching to find the correct postal code"
        )

if __name__ == "__main__":
    # Setup Logging Configs
    logging.basicConfig(level=logging.INFO)