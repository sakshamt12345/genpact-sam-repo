from crewai import Agent, Task, Crew, Process
from crewai.project import CrewBase, agent, task

from software_asset_management.tools.authentication_tool import Authentication
from software_asset_management.tools.software_library_tool import SoftwareLibraryTool
from software_asset_management.tools.software_details_tool import SoftwareDetailsTool
from software_asset_management.tools.assignment_check_tool import AssignmentCheckTool
from software_asset_management.tools.device_lookup_tool import DeviceLookupTool
from software_asset_management.tools.software_license_check_tool import SoftwareLicenseCheckTool
from software_asset_management.tools.duplicate_ticket_check_tool import DuplicateTicketCheck
from software_asset_management.tools.ritm_detail_tool import RITMDetails
from software_asset_management.tools.software_installation_tool import SoftwareInstallation
from software_asset_management.tools.software_freeware_request_tool import SoftwareRequest

from software_asset_management.models import IntentClassification
from software_asset_management.models import SoftwareResolution, SoftwareDetailsResult, AssignmentCheckResult
from software_asset_management.models import DeviceLookupResult
from software_asset_management.models import SoftwareLicenseCheckResult, SoftwareLicenseResolution
from software_asset_management.models import TicketLookupResult, TicketDuplicateCheckResult
from software_asset_management.models import SoftwarePushResult, RITMGenerationResult


@CrewBase
class SAMCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def authentication_agent(self) -> Agent:
        return Agent(config=self.agents_config["authentication_agent"], tools=[Authentication()])

    @agent
    def intent_classifier_agent(self) -> Agent:
        return Agent(config=self.agents_config["intent_classifier_agent"])

    @agent
    def install_agent(self) -> Agent:
        return Agent(config=self.agents_config["install_agent"],tools=[SoftwareLibraryTool(), SoftwareDetailsTool(), AssignmentCheckTool()],)

    @agent
    def device_agent(self) -> Agent:
        return Agent(config=self.agents_config["device_agent"],tools=[DeviceLookupTool()],)

    @agent
    def license_agent(self) -> Agent:
        return Agent(config=self.agents_config["license_agent"],tools=[SoftwareLicenseCheckTool()],)

    @agent
    def ticket_agent(self) -> Agent:
        return Agent(config=self.agents_config["ticket_agent"],tools=[DuplicateTicketCheck(), RITMDetails()],)

    @agent
    def installation_request_agent(self) -> Agent:
        return Agent(config=self.agents_config["installation_request_agent"],tools=[SoftwareInstallation(), SoftwareRequest()],)

    @task
    def authentication_task(self) -> Task:
        return Task(config=self.tasks_config["authentication_task"])

    @task
    def classify_intent_task(self) -> Task:
        return Task(config=self.tasks_config["classify_intent_task"], output_pydantic=IntentClassification)

    @task
    def resolve_software_task(self) -> Task:
        return Task(config=self.tasks_config["resolve_software_task"],output_pydantic=SoftwareResolution)

    @task
    def get_software_details_task(self) -> Task:
        return Task(config=self.tasks_config["get_software_details_task"], output_pydantic=SoftwareDetailsResult)

    @task
    def check_assignment_task(self) -> Task:
        return Task(config=self.tasks_config["check_assignment_task"], output_pydantic=AssignmentCheckResult)

    @task
    def fetch_devices_task(self) -> Task:
        return Task(config=self.tasks_config["fetch_devices_task"], output_pydantic=DeviceLookupResult)
    @task
    def classify_and_resolve_license_task(self) -> Task:
        return Task(config=self.tasks_config["classify_and_resolve_license_task"], output_pydantic=SoftwareLicenseResolution)

    @task
    def check_license_task(self) -> Task:
        return Task(config=self.tasks_config["check_license_task"], output_pydantic=SoftwareLicenseCheckResult)

    @task
    def check_ticket_and_duplicate_task(self) -> Task:
        return Task(config=self.tasks_config["check_ticket_and_duplicate_task"], output_pydantic=TicketDuplicateCheckResult)

    @task
    def push_software_task(self) -> Task:
        return Task(config=self.tasks_config["push_software_task"], output_pydantic=SoftwarePushResult)

    @task
    def generate_ritm_task(self) -> Task:
        return Task(config=self.tasks_config["generate_ritm_task"], output_pydantic=RITMGenerationResult)

    def auth_crew(self) -> Crew:
        return Crew(agents=[self.authentication_agent()], tasks=[self.authentication_task()], process=Process.sequential, verbose=True)

    def intent_crew(self) -> Crew:
        return Crew(agents=[self.intent_classifier_agent()], tasks=[self.classify_intent_task()], process=Process.sequential, verbose=True)

    def resolve_software_crew(self) -> Crew:
        return Crew(agents=[self.install_agent()],tasks=[self.resolve_software_task()],process=Process.sequential,verbose=True)

    def software_details_crew(self) -> Crew:
        return Crew(agents=[self.install_agent()], tasks=[self.get_software_details_task()], process=Process.sequential, verbose=True)

    def assignment_crew(self) -> Crew:
        return Crew(agents=[self.install_agent()], tasks=[self.check_assignment_task()], process=Process.sequential, verbose=True)

    def device_crew(self) -> Crew:
         return Crew(agents=[self.device_agent()], tasks=[self.fetch_devices_task()], process=Process.sequential, verbose=True)

    def license_resolution_crew(self) -> Crew:
        return Crew(agents=[self.license_agent()], tasks=[self.classify_and_resolve_license_task()], process=Process.sequential, verbose=True)

    def license_check_crew(self) -> Crew:
        return Crew(agents=[self.license_agent()], tasks=[self.check_license_task()], process=Process.sequential, verbose=True)

    def ticket_check_crew(self) -> Crew:
        return Crew(agents=[self.ticket_agent()], tasks=[self.check_ticket_and_duplicate_task()], process=Process.sequential, verbose=True)

    def push_software_crew(self) -> Crew:
        return Crew(agents=[self.installation_request_agent()], tasks=[self.push_software_task()], process=Process.sequential, verbose=True)

    def generate_ritm_crew(self) -> Crew:
        return Crew(agents=[self.installation_request_agent()], tasks=[self.generate_ritm_task()], process=Process.sequential, verbose=True)





