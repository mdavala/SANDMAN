import re, json
import logging

logger = logging.getLogger(__name__)
 
def extract_json_from_string(text):
    """Extract JSON content from markdown code blocks or plain text"""
    # Remove ```json and ``` markers if present
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        json_string = json_match.group(1)
    else:
        # If no markdown markers, assume the whole string is JSON
        json_string = text.strip()
    
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON: {e}")
        return None
        
def check_json(data):
    if not data:
        return True, []
        
    sites = data.get("l2vpn_svc", {}).get("sites", {}).get("site", [])
    logger.info(f"sites: {sites}")

    for site in sites:
        accesses = site.get("site_network_accesses", {}).get("site_network_access", [])
        for access in accesses:
            eth_inf_type = access.get("connection", {}).get("eth_inf_type", "")
            if eth_inf_type and not eth_inf_type.startswith("{"):
                logger.info(f"[OK] eth_inf_type is filled: {eth_inf_type} for site {site.get('site_id')}")
                return True, sites
            else:
                logger.info(f"[MISSING] eth_inf_type is not filled or placeholder for site {site.get('site_id')}")
                return False, sites
    return True, sites

def clean_string(input_string: str, fallback: str = "unknown") -> str:
    """
    Clean any string by removing ALL special characters (including underscores and spaces)
    
    Args:
        input_string: Original string that may contain special characters
        fallback: Fallback string to use if input is empty or None (default: "unknown")
        
    Returns:
        Cleaned string with ONLY alphanumeric characters (letters and numbers)
    """
    if not input_string:
        return fallback
    
    # Convert to lowercase and remove ALL special characters (keep only letters and numbers)
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', input_string.lower())
    
    # Ensure it's not empty after cleaning
    if not cleaned:
        return fallback
    
    # Ensure it doesn't start with a number (prefix with letters only)
    if cleaned[0].isdigit():
        cleaned = f"str{cleaned}"
    
    return cleaned


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)