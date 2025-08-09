🏗️ SANDMAN - Multi-Agent Service Orchestrator
Smart Automated Network Deployment and Management Agent Network
SANDMAN is an intelligent Infrastructure as a Service (IAAS) management system that leverages multiple AI agents to orchestrate network services through natural language conversation. It provides conversational interface configuration for complex network services like EVPN VPWS, L3VPN, and L2Circuit provisioning.

**🌟 Features
🤖 Multi-Agent Architecture**
1. **MSO Triage Agent:** Intelligent request routing and coordination
2. **Routing Director Agent:** Network service provisioning (EVPN VPWS/ELAN, L3VPN, L2Circuit)
3. **Security Director Agent:** Security policy and firewall management
4. **Apstra Agent:** Data center fabric and topology management
5. **Interface Configuration Assistant:** Conversational interface setup with validation

**💬 Conversational Interface Configuration**
1. Natural language service configuration
2. Interactive parameter collection for tagged/untagged interfaces
3. Real-time validation and status tracking
4. Automatic JSON generation with user-provided parameters

**🧠 Persistent Session Memory**
1. SQLite-based conversation history
2. Session-aware context retention
3. Multi-session management support

**🎯 Service Management**
1. EVPN VPWS service creation and deployment
2. Customer and device management
3. Service validation and resource placement
4. Brownfield L2VPN BGP signaling discovery

**🖥️ Modern Web Interface**
1. Streamlit-based responsive GUI
2. Real-time chat with AI agents
3. Configuration download and auto-save
4. Agent activity monitoring and statistics

**🛠️ Prerequisites**
* Python 3.8+
* OpenAI API key (GPT-4 recommended)
* Anthropic API key (optional)
* Access to Routing Director API instance
* Git for cloning the repository

**🚀 Installation**
**1. Clone the Repository**
git clone https://github.com/mdavala/SANDMAN.git
cd SANDMAN

**2. Create Virtual Environment**
python -m venv .sandman-env
source .sandman-env/bin/activate  # On Windows: .sandman-env\Scripts\activate

**3. Install Dependencies**
pip install -r requirements.txt

**4. Create Required Directories**
mkdir sessions payload

**⚙️ Configuration**
**1. Environment Setup**
Create a .env file in the project root with the following configuration:
# LLM Credentials/API-Keys
OPENAI_API_KEY="sk-proj-your-openai-key-here"
ANTHROPIC_API_KEY="sk-ant-api-your-anthropic-key-here"

# Routing Director Credentials
USERNAME="your-username"
PASSWORD="your-password" 
ORG_ID="your-org-id"
BASE_URL="https://66.129.234.204:48800" #Routing Director BASE_URL
TOPO_FILE_NAME="your-topology-file"
RD_RT_RESOURCES="your-resources"

# Routing Base API Endpoints (DO NOT MODIFY)
CUSTOMERS_API_ENDPOINT="/service-orchestration/api/v1/orgs/{org_id}/order/customers"
DEVICES_API_ENDPOINT="/trust/api/v1.1alpha/{org_id}/devices"
SITES_API_ENDPOINT="/api/v1/orgs/{org_id}/sites"
TOPO_API_ENDPOINT="/api-aggregator/api/v1/orgs/{org_id}/aggregate/network-resources-by-instance?customer_id={infra_id}&instance_id={topo_file_name}"

**2. Required Credentials**

**OPENAI_API_KEY:** Your OpenAI API key for GPT-4 access
**ANTHROPIC_API_KEY:** Your Anthropic API key (optional, for Claude models)
**USERNAME/PASSWORD:** Routing Director system credentials
**ORG_ID:** Your organization identifier in Routing Director
**TOPO_FILE_NAME:** Topology file name for network resources
**RD_RT_RESOURCES:** Resource configuration for Routing Director
**⚠️ Important:** The Routing Base API Endpoints are pre-configured and should not be modified.


**🎮 Usage**
**1. Start the Web Interface**
streamlit run sandmanGUI.py
The web interface will be available at http://localhost:8501

**2. Using the Chat Interface**
**Start conversations with natural language commands:**
"Create EVPN VPWS service for customer ABC between Cambodia and Thailand sites"
"Show all existing EVPN services"
"Delete service xyz123"

**3. Conversational Interface Configuration**
When creating services, SANDMAN will guide you through interface configuration:
**For Tagged Interfaces:**
SANDMAN: "For site kh_site1, what interface type: tagged or untagged?"
You: "tagged"
SANDMAN: "For tagged interface, please provide: speed (Mbps), LLDP (true/false), OAM (true/false)"  
You: "10000, true, false"
**For Untagged Interfaces:**
SANDMAN: "For site th_site1, what interface type: tagged or untagged?"
You: "untagged"
SANDMAN: "For untagged interface, please provide CVLAN ID (1-4094):"
You: "200"

**4. Configuration Management**
**Auto-Save:** Completed configurations are automatically saved to payload/ directory
**Download:** Use the web interface to download JSON configurations
**Session Memory:** Conversations are preserved across browser sessions

**🏗️ Architecture**
**Directory Structure**
SANDMAN/
├── rdMCPServer.py           # Routing Director MCP Server
├── mso.py                   # Multi-Service Orchestrator Agent
├── sandmanGUI.py           # Streamlit Web Interface
├── servicesAgent.py        # Service management logic
├── instructions_template.py # Agent instruction templates
├── .env                    # Environment configuration
├── requirements.txt        # Python dependencies
├── sessions/              # SQLite session storage
├── payload/               # Generated configurations
└── README.md              # This file

**Agents Flow**
User Input → MSO Triage Agent → Specialist Agents → Interface Config Assistant → Final JSON

**Data Flow**
1. **Input Processing:** Natural language → Intent classification
2. **Agent Routing:** MSO routes to appropriate specialist agent
3. **Service Generation: **Base configuration creation
4. **Interface Configuration:** Conversational parameter collection
5. **Validation:** Real-time parameter validation
6. **Output Generation:** Final JSON configuration with auto-save

**📋 Supported Services**
**Network Services**
EVPN VPWS: Ethernet VPN Virtual Private Wire Service

**Management Operations**
* Customer creation and management
* Service discovery and inventory
* Resource validation and placement
* Service deployment and lifecycle management

**🔧 API Endpoints**
The system integrates with the following API endpoints (pre-configured):
Endpoint --- Purpose
/service-orchestration/api/v1/orgs/{org_id}/order/customers --- Customer management
/trust/api/v1.1alpha/{org_id}/devicesDevice --- Devices inventory
/api/v1/orgs/{org_id}/sites --- Sites Inventory 
/api-aggregator/api/v1/orgs/{org_id}/aggregate/network-resources-by-instance --- Resource Topology File


**🐛 Troubleshooting**
**Common Issues**
**1. API Connection Errors**
* Verify Routing Director credentials in .env
* Check network connectivity to BASE_URL
* Ensure ORG_ID is correct

**2. Missing Dependencies**
pip install --upgrade -r requirements.txt

**3. Session Memory Issues**
* Check sessions/ directory permissions
* Clear session data: Delete .db files in sessions/

**4. Interface Configuration Errors**
* Ensure valid parameter ranges (CVLAN: 1-4094, Speed: numeric)
* Use exact values: "tagged"/"untagged", true/false

**Logging**
**Enable debug logging by setting:**
logging.basicConfig(level=logging.DEBUG)

**🤝 Contributing**

1. Fork the repository
2. Create a feature branch (git checkout -b feature/amazing-feature)
3. Commit your changes (git commit -m 'Add amazing feature')
4. Push to the branch (git push origin feature/amazing-feature)
5. Open a Pull Request

**📝 License**
This project is licensed under the MIT License - see the LICENSE file for details.
