from email import message
import re
from unittest import result
from crewai import Flow, LLM
from crewai import flow
from crewai.flow import listen, ConversationConfig, ConversationState
import os

from datetime import date, timedelta
import dateutil.parser
from dateutil.relativedelta import relativedelta

from httpx import options
from software_asset_management.crews.SAM_crew.sam_crew import SAMCrew
from software_asset_management.models import SoftwareResolution, IntentClassification, SoftwareDetailsResult, DeviceLookupResult, AssignmentCheckResult, SoftwareLicenseCheckResult, SoftwareLicenseResolution, TicketDuplicateCheckResult, SoftwarePushResult, RITMGenerationResult

llm = LLM(
    model=os.getenv("MODEL"),
    api_key=os.getenv("AZURE_API_KEY"),
    base_url=os.getenv("AZURE_API_BASE"),
    api_version=os.getenv("AZURE_API_VERSION"),
)


class SAMState(ConversationState):
    #Flow Default Value
    #Current User
    ohr: int = None
    verified: bool = False

    #On-Behalf User
    awaiting_target_ohr: bool = False
    awaiting_confirmation: bool = False
    target_ohr: int = None
    target_name: str = None

    #Software Name and Operation
    pending_request_type: str = None #[Install,Update,Renew,Transfer,Uninstall]
    pending_software_name: str = None

    request_mode: str = "install"   # "install" or "update"
    awaiting_install_from_update_confirmation: bool = False

    #Software Name Handling
    awaiting_software_confirmation: bool = False
    software_candidates: list = []
    confirmed_software: str = None
    awaiting_software_clarification: bool = False
    resolved_software_details: dict = None

    #Blacklisted Handling
    awaiting_blacklist_ticket_confirmation: bool = False
    blacklisted_software_name: str = None

    #Single and Multi Device Handling
    awaiting_device_selection: bool = False
    device_options: list = []
    selected_serial: str = None

    #Version Assigment Handling
    awaiting_version_selection: bool = False
    version_selection_mode: str = None   
    version_options: list = []           
    version_options_full: list = []      
    awaiting_assignment_ticket_confirmation: bool = False
    last_assignment_records: list = []
    post_version_selection_action: str = None
    single_version_auto_selected: bool = False

    #Update Software Handling
    awaiting_update_confirmation: bool = False
    installed_versions_for_update: list = []

    #Microsoft License Check
    software_category: str = None
    pending_license_check_category: str = None
    pending_license_name: str = None

    #Tool Tip
    free_alternatives: list = []

    #Ticket Creation Handling
    pending_ticket_kind: str = None
    pending_ticket_flag: str = None
    awaiting_notassigned_ticket_intent: bool = False
    not_assigned_software: str = None
    not_assigned_prefix: str = None
    awaiting_cost_confirmation: bool = False
    cost_confirm_version: dict = None
    ticket_start_date: str = None
    ticket_end_date: str = None

    awaiting_duration_input: bool = False
    ticket_duration_months: int = None

    # Renewal Handling
    awaiting_renewal_ticket_confirmation: bool = False
    renewal_installed_versions: list = []
    renewal_software_name: str = None

@ConversationConfig(defer_trace_finalization=True)
class SAMFlow(Flow[SAMState]):
    #Conversational Enabled
    conversational = True
    #Routing Logic of SAM
    def route_turn(self, context):
        if not self.state.verified:
            return "authenticate"
        if self.state.awaiting_target_ohr:
            return "authenticate_target"
        if self.state.awaiting_confirmation:
            return "confirm_target"
        if self.state.awaiting_software_confirmation:
            return "confirm_software"
        if self.state.awaiting_software_clarification:
            return "clarify_software"
        if self.state.awaiting_blacklist_ticket_confirmation:
            return "confirm_blacklist_ticket"
        if self.state.awaiting_device_selection:
            return "select_device"
        if self.state.awaiting_version_selection:
            return "select_version"
        if self.state.awaiting_assignment_ticket_confirmation:
            return "confirm_assignment_ticket"
        if self.state.awaiting_update_confirmation:
            return "confirm_update"
        if self.state.awaiting_notassigned_ticket_intent:
            return "notassigned_ticket_intent"
        if self.state.awaiting_cost_confirmation:
            return "confirm_cost"
        if self.state.awaiting_duration_input:
            return "collect_duration"
        if self.state.awaiting_install_from_update_confirmation:
            return "confirm_install_from_update"
        if self.state.awaiting_renewal_ticket_confirmation:
            return "confirm_renewal_ticket"

        message = (self.state.current_user_message or "").lower()
        if "bye" in message or "exit" in message or "quit" in message:
         return "exit_conversation"
        return "process_query"

    #State Fuctions
    #Authentication Handler
    @listen("authenticate")
    def handle_authentication(self) -> str:
        message = self.state.current_user_message or "" # Last user message
        match = re.search(r"\b\d{9}\b", message) # Search for a 9-digit OHR in the message

        if not match:
            reply = "Invalid OHR. Please enter a valid 9-digit OHR." # Reply if no valid OHR is found
            self.append_assistant_message(reply) # Append the assistant's message to the conversation history
            return reply

        self.state.ohr = int(match.group()) # Store the extracted OHR in the conversation state
        result = SAMCrew().auth_crew().kickoff(inputs={"ohr": self.state.ohr}) # Kick off the authentication crew with the extracted OHR
        result_text = str(result) # Convert the result to a string for further processing

        if "denied" in result_text.lower() or "failed" in result_text.lower() or "not authorized" in result_text.lower(): # Check for failure keywords in the result text
            reply = "Verification failed. Please enter a valid OHR." # Reply if verification fails
            self.append_assistant_message(reply) # Append the assistant's message to the conversation history
            return reply # Return the reply

        self.state.verified = True # Mark the user as verified in the conversation state
        reply = "Enter your query" # Reply to prompt the user to enter their query after successful verification
        self.append_assistant_message(reply) 
        return reply
    
    @listen("authenticate_target")
    def handle_authenticate_target(self) -> str:
        message = self.state.current_user_message or ""
        match = re.search(r"\b\d{9}\b", message) #

        if not match:
            reply = "That doesn't look like a valid 9-digit OHR — mind double-checking and sending it again?"
            self.append_assistant_message(reply)
            return reply

        return self._verify_and_confirm_target(int(match.group()))

    #Intent Classification Handler
    @listen("process_query")
    def handle_user_query(self) -> str:
        message = self.state.current_user_message or ""

        result = SAMCrew().intent_crew().kickoff(inputs={
            "ohr": self.state.ohr,
            "user_message": message,
        })
        intent: IntentClassification = result.pydantic

        if intent.request_for == "someone_else":
            self.state.pending_request_type = intent.request_type
            self.state.pending_software_name = intent.software_name or ""

            match = re.search(r"\b\d{9}\b", message)
            if match and int(match.group()) != self.state.ohr:
                return self._verify_and_confirm_target(int(match.group()))

            self.state.awaiting_target_ohr = True
            name_hint = f" for {intent.on_behalf_of}" if intent.on_behalf_of else ""
            reply = (
                f"No problem, happy to help{name_hint}! "
                f"Could you share their 9-digit OHR so I can pull up their details?"
            )
            self.append_assistant_message(reply)
            return reply

        if intent.request_type in ("Install", "Update", "Renew") and intent.software_name:
            self.state.request_mode = {
                "Install": "install",
                "Update": "update",
                "Renew": "renew",
            }[intent.request_type]

            return self._resolve_software(intent.software_name)

        if intent.request_type == "General Query":
            reply = "I'm not quite sure I follow — could you rephrase that, or let me know what you'd like help with?"
            self.append_assistant_message(reply)
            return reply

        # Uninstall / Renew / Transfer / Update — not yet built, acknowledge gracefully
        reply = f"Got it — looks like you're looking to **{intent.request_type.lower()}**"
        if intent.software_name:
            reply += f" **{intent.software_name}**"
        reply += ", but that workflow isn't available just yet. I can currently help with software installs — let me know if you'd like to install something instead."
        self.append_assistant_message(reply)
        return reply

    @listen("clarify_software")
    def handle_clarify_software(self) -> str:
        software_name = (self.state.current_user_message or "").strip()
        return self._resolve_software(software_name)

    @listen("select_device")
    def handle_select_device(self) -> str:
        message = (self.state.current_user_message or "").strip()
        options = self.state.device_options

        chosen = None
        if message.isdigit() and 1 <= int(message) <= len(options):
            chosen = options[int(message) - 1]
        else:
            for opt in options:
                if opt["serial_number"].lower() in message.lower() or opt["model"].lower() in message.lower():
                    chosen = opt
                    break

        if not chosen:
            options_list = "\n".join(f"{i+1}. {d['model']} (Serial: {d['serial_number']})" for i, d in enumerate(options))
            reply = f"Sorry, I didn't catch that. Please pick one:\n\n{options_list}"
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_device_selection = False
        self.state.device_options = []
        self.state.selected_serial = chosen["serial_number"]

        return self._route_by_category(self.state.confirmed_software)

    @listen("select_version")
    def handle_select_version(self) -> str:
        message = (self.state.current_user_message or "").strip()
        options = self.state.version_options
        mode = self.state.version_selection_mode
        full = self.state.version_options_full
        category = (self.state.software_category or "").lower()
        print(f"DEBUG select_version: mode={mode}, category={category}, single_version_auto_selected={self.state.single_version_auto_selected}")

        # --- Single-version auto-selection (yes/no confirmation instead of numbered pick) ---
        if self.state.single_version_auto_selected:
            decision = self.classify_intent(message, ("CONFIRMED", "DENIED", "UNCLEAR"), llm=llm)
            if decision == "DENIED":
                self.state.awaiting_version_selection = False
                self.state.single_version_auto_selected = False
                self.state.version_options = []
                self.state.version_options_full = []
                reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
                self.append_assistant_message(reply)
                return reply
            if decision == "UNCLEAR":
                reply = "Just to confirm — would you like to proceed with this version? (yes/no)"
                self.append_assistant_message(reply)
                return reply
            # CONFIRMED — treat as if they picked option "1"
            self.state.single_version_auto_selected = False
            message = "1"

        label_key = "assigned_version" if mode == "assigned" else "version"

        # --- "More" — works for any mode, shows the full list re-numbered ---
        if message.isdigit() and int(message) == len(options) + 1 and len(full) > len(options):
            self.state.version_options = full
            version_list = "\n".join(f"{i+1}. V.{v.get(label_key)}" for i, v in enumerate(full))
            reply = f"Here are all versions:\n\n{version_list}\n\nWhich one would you like?"
            self.append_assistant_message(reply)
            return reply

        # --- Match the user's selection ---
        chosen = None
        if message.isdigit() and 1 <= int(message) <= len(options):
            chosen = options[int(message) - 1]
        else:
            for opt in options:
                label = opt.get(label_key) or ""
                if label.lower() in message.lower():
                    chosen = opt
                    break

        if not chosen:
            version_list = "\n".join(f"{i+1}. V.{v.get(label_key)}" for i, v in enumerate(options))
            reply = f"Sorry, I didn't catch that. Please pick one:\n\n{version_list}"
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_version_selection = False
        self.state.version_options = []
        self.state.version_options_full = []

        chosen_version = chosen.get(label_key)

        # --- Mode: assigned (device already has this software assigned) ---
        if mode == "assigned":
            self.state.version_selection_mode = None

            if self.state.post_version_selection_action == "ticket":
                self.state.post_version_selection_action = None
                self.state.awaiting_assignment_ticket_confirmation = True
                reply = f"Would you like me to raise a request ticket to get **V.{chosen_version}** installed?"
                self.append_assistant_message(reply)
                return reply

            reply = f"Got it — **V.{chosen_version}** selected."
            self.append_assistant_message(reply)
            return reply

        # --- Mode: available (nothing assigned, picking from catalog after ticket-intent confirmed) ---
        self.state.version_selection_mode = None
        print(f"DEBUG available-branch: category={category}, chosen_version={chosen_version}")

        if category == "license":
            self.state.awaiting_cost_confirmation = True
            self.state.cost_confirm_version = chosen
            cost = self._format_cost(chosen.get("cost"))
            raw_tool_tip = chosen.get("tool_tip") or ""
            cleaned_tip, alternatives = self._parse_tool_tip(raw_tool_tip)
            self.state.free_alternatives = alternatives

            reply = f"V.{chosen_version} is available for **{cost}**."
            if cleaned_tip:
                reply += f" {cleaned_tip}"
            if alternatives:
                names = ", ".join(a["display"] for a in alternatives)
                reply += f"\n\nThere are also free alternatives available: {names}."
            reply += "\n\nWould you like to proceed?"

            self.append_assistant_message(reply)
            return reply

        self.state.cost_confirm_version = chosen   # carried through for handle_collect_duration to read back
        self.state.awaiting_duration_input = True
        reply = (
            "Please select the duration for which the software is required.\n\n"
            "Note: The maximum allowable duration is up to 12 months from the start date."
        )
        self.append_assistant_message(reply)
        return reply

    @listen("notassigned_ticket_intent")
    def handle_notassigned_ticket_intent(self) -> str:
        message = self.state.current_user_message or ""
        decision = self.classify_intent(message, ("CONFIRMED", "DENIED", "UNCLEAR"), llm=llm)

        if decision == "DENIED":
            self.state.awaiting_notassigned_ticket_intent = False
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        if decision == "UNCLEAR":
            reply = f"Just to confirm — would you like to request a ticket for **{self.state.not_assigned_software}**? (yes/no)"
            self.append_assistant_message(reply)
            return reply

        # CONFIRMED — now show the version list
        self.state.awaiting_notassigned_ticket_intent = False
        resolved_name = self.state.not_assigned_software

        details = self.state.resolved_software_details or {}
        all_versions = details.get("versions") or []

        self.state.version_selection_mode = "available"
        self.state.version_options_full = all_versions

        if len(all_versions) == 1:
            v = all_versions[0]
            self.state.version_options = all_versions
            self.state.awaiting_version_selection = True
            self.state.single_version_auto_selected = True
            reply = f"Only V.{v.get('version')} is available. Would you like to proceed with this version?"
            self.append_assistant_message(reply)
            return reply

        top5 = all_versions[:5]
        self.state.version_options = top5
        self.state.awaiting_version_selection = True
        version_list = "\n".join(f"{i+1}. V.{v.get('version')}" for i, v in enumerate(top5))
        more_line = f"\n{len(top5)+1}. More" if len(all_versions) > 5 else ""
        reply = f"Here are the available versions of **{resolved_name}**:\n\n{version_list}{more_line}\n\nWhich one would you like?"
        self.append_assistant_message(reply)
        return reply


    #Helper Functions
    #Calling From authenticate_target and process_query
    def _verify_and_confirm_target(self, target_ohr: int) -> str:
        result = SAMCrew().auth_crew().kickoff(inputs={"ohr": target_ohr})
        result_text = str(result)

        if "denied" in result_text.lower() or "failed" in result_text.lower() or "not authorized" in result_text.lower():
            self.state.awaiting_target_ohr = True
            reply = "I couldn't verify that OHR — could you confirm and send it again?"
            self.append_assistant_message(reply)
            return reply

        name_match = re.search(r"Name:\s*(.+)", result_text)
        target_name = name_match.group(1).strip() if name_match else "this person"

        self.state.target_ohr = target_ohr
        self.state.target_name = target_name
        self.state.awaiting_target_ohr = False
        self.state.awaiting_confirmation = True

        reply = f"Just to confirm — this is for **{target_name}**, is that right?"
        self.append_assistant_message(reply)
        return reply

    def _resolve_software(self, software_name: str) -> str:
        self.state.version_selection_mode = None
        self.state.version_options = []
        self.state.version_options_full = []
        self.state.post_version_selection_action = None
        self.state.single_version_auto_selected = False
        self.state.cost_confirm_version = None
        self.state.free_alternatives = []
        # NOTE: do NOT reset request_mode here — it's set by the caller (handle_user_query)
        # right before calling this function, so resetting it here would wipe that out.

        resolution_result = SAMCrew().resolve_software_crew().kickoff(inputs={"software_name": software_name})
        resolution: SoftwareResolution = resolution_result.pydantic

        if resolution.confidence == "high" and resolution.matched_software:
            self.state.awaiting_software_clarification = False
            self._fetch_and_store_details(resolution.matched_software)

            blacklist_reply = self._check_blacklist_and_reply(resolution.matched_software)
            if blacklist_reply:
                return blacklist_reply

            return self._after_blacklist_clear(resolution.matched_software)

        if resolution.confidence == "ambiguous" and resolution.candidates:
            self.state.awaiting_software_clarification = False
            self.state.software_candidates = [c.unique_name for c in resolution.candidates]
            self.state.awaiting_software_confirmation = True
            options_list = "\n".join(f"{i+1}. {c.unique_name}" for i, c in enumerate(resolution.candidates))
            reply = f"There are a few distinct products matching \"{software_name}\":\n\n{options_list}\n\nWhich one would you like?"
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_software_clarification = True
        reply = f"I couldn't find \"{software_name}\" in our registered software catalog. Could you clarify the exact name?"
        self.append_assistant_message(reply)
        return reply

    def _fetch_and_store_details(self, resolved_name: str) -> None:
        details_result = SAMCrew().software_details_crew().kickoff(inputs={"resolved_software": resolved_name})
        details: SoftwareDetailsResult = details_result.pydantic
        self.state.resolved_software_details = details.model_dump()

    def _check_blacklist_and_reply(self, resolved_name: str) -> str:
        """After details are fetched, check blacklist status. Returns the reply text,
        or None if not blacklisted (caller should proceed with its own normal message)."""
        details = self.state.resolved_software_details or {}
        versions = details.get("versions", [])

        # if versions and all(v.get("blacklisted") for v in versions):
        #     self.state.awaiting_blacklist_ticket_confirmation = True
        #     self.state.blacklisted_software_name = resolved_name
        #     reply = (
        #         f"**{resolved_name}** is currently blacklisted and not available for direct install. "
        #         f"Would you like me to raise a request ticket for it instead?"
        #     )
        #     self.append_assistant_message(reply)
        #     return reply

        if versions and all(v.get("blacklisted") for v in versions):
            context = f"**{resolved_name}** is currently restricted and not available for direct install."
            return self._offer_ticket_or_show_existing(resolved_name, ticket_kind="blacklist", context_message=context)

        return None

    def _after_blacklist_clear(self, resolved_name: str) -> str:
        self.state.confirmed_software = resolved_name
        ohr_for_device = self.state.target_ohr if self.state.target_ohr else self.state.ohr

        device_result = SAMCrew().device_crew().kickoff(inputs={"ohr": ohr_for_device})
        devices: DeviceLookupResult = device_result.pydantic

        if not devices.devices:
            reply = "I couldn't find any registered device for this employee. Please reach out to IT to register a device first."
            self.append_assistant_message(reply)
            return reply

        if len(devices.devices) == 1:
            self.state.selected_serial = devices.devices[0].serial_number
            return self._route_by_category(resolved_name)

        self.state.device_options = [d.model_dump() for d in devices.devices]
        self.state.awaiting_device_selection = True
        options_list = "\n".join(
            f"{i+1}. {d.model} (Serial: {d.serial_number})"
            for i, d in enumerate(devices.devices)
        )
        reply = f"I found multiple devices registered. Which one would you like to use?\n\n{options_list}"
        self.append_assistant_message(reply)
        return reply

    def _route_by_category(self, resolved_name: str) -> str:
        details = self.state.resolved_software_details or {}
        versions = details.get("versions") or []
        category = (versions[0].get("category") if versions else "").lower()

        self.state.software_category = category

        # Renew has its own flow.
        # It works regardless of software category or version.
        if self.state.request_mode == "renew":
            return self._handle_renewal_flow(resolved_name)

        if category == "license":
            return self._handle_license_flow(resolved_name)

        return self._check_assignment_and_reply(
            resolved_name,
            self.state.selected_serial
        )


    def _handle_license_flow(self, resolved_name: str) -> str:
        resolution_result = SAMCrew().license_resolution_crew().kickoff(inputs={"software_name": resolved_name})
        resolution: SoftwareLicenseResolution = resolution_result.pydantic
        print(f"DEBUG: is_microsoft_product={resolution.is_microsoft_product}, actual_license_name={resolution.actual_license_name}, category={resolution.category}")

        if not resolution.is_microsoft_product:
            return self._check_assignment_and_reply(resolved_name, self.state.selected_serial)

        if not resolution.actual_license_name or not resolution.category:
            reply = f"**{resolved_name}** is a Microsoft product, but I couldn't find a matching entry in the license reference table. Escalating for manual review."
            self.append_assistant_message(reply)
            return reply

        ohr_for_check = self.state.target_ohr if self.state.target_ohr else self.state.ohr
        check_result = SAMCrew().license_check_crew().kickoff(inputs={
            "ohr": ohr_for_check,
            "license_category": resolution.category,
            "license_name": resolution.actual_license_name,
        })
        check: SoftwareLicenseCheckResult = check_result.pydantic
        is_member = "not part of" not in check.response.lower()
        print(f"DEBUG: check.response={check.response!r}, is_member={is_member}")

        if not is_member:
            context = f"You're not currently part of the **{check.group_name}** group required for **{resolved_name}**."
            return self._create_ticket_or_show_existing(f"{resolved_name} ({check.group_name} access)", ticket_kind="license_access", context_message=context)

        # is_member == True — show cost + tool_tip, confirm before proceeding to ticket
        details = self.state.resolved_software_details or {}
        versions = details.get("versions") or []
        print(f"DEBUG: entered is_member branch, versions_count={len(versions)}")
        if not versions:
            reply = f"You're part of the **{check.group_name}** group, but I couldn't find version details for **{resolved_name}**."
            self.append_assistant_message(reply)
            return reply

        v = versions[0]
        cost = self._format_cost(v.get("cost"))
        raw_tool_tip = v.get("tool_tip") or ""
        cleaned_tip, alternatives = self._parse_tool_tip(raw_tool_tip)
        self.state.free_alternatives = alternatives
        self.state.cost_confirm_version = v
        self.state.awaiting_cost_confirmation = True

        reply = f"You're part of the **{check.group_name}** group. **{resolved_name}** V.{v.get('version')} is available for **{cost}**."
        if cleaned_tip:
            reply += f" {cleaned_tip}"
        if alternatives:
            names = ", ".join(a["display"] for a in alternatives)
            reply += f"\n\nThere are also free alternatives available: {names}."
        reply += "\n\nWould you like to proceed?"

        self.append_assistant_message(reply)
        return reply
    
    def _check_assignment_and_reply(self, resolved_name: str, serial_number: str, prefix: str = "") -> str:
        ohr_for_check = self.state.target_ohr if self.state.target_ohr else self.state.ohr

        result = SAMCrew().assignment_crew().kickoff(inputs={
            "ohr": ohr_for_check,
            "serial_number": serial_number,
            "software_name": resolved_name,
        })
        assignment: AssignmentCheckResult = result.pydantic
        assigned_records = [r for r in assignment.records if r.assigned_status]
        print(f"DEBUG assignment_check: software={resolved_name}, assigned_count={len(assigned_records)}, raw_records={[r.model_dump() for r in assignment.records]}")

        return self._display_versions_for_selection(resolved_name, assigned_records, prefix=prefix)

    def _display_versions_for_selection(self, resolved_name: str, assigned_records: list, prefix: str = "") -> str:
        self.state.last_assignment_records = [r.model_dump() for r in assigned_records]
        installed = [r for r in assigned_records if r.installed_status]
        category = (self.state.software_category or "").lower()

        if installed:
            versions = [r.assigned_version for r in installed]
            version_text = ", ".join(f"V.{v}" for v in versions)
            self.state.installed_versions_for_update = [r.model_dump() for r in installed]
            self.state.awaiting_update_confirmation = True
            reply = prefix + f"Looks like **{resolved_name}** ({version_text}) is already installed on your system. Would you like to update it to a newer version?"
            self.append_assistant_message(reply)
            return reply

        if assigned_records:
            self.state.version_selection_mode = "assigned"
            self.state.version_options_full = [r.model_dump() for r in assigned_records]

            action_word = "update to" if self.state.request_mode == "update" else "select"

            if len(self.state.version_options_full) == 1:
                v = self.state.version_options_full[0]
                self.state.version_options = self.state.version_options_full
                self.state.awaiting_version_selection = True
                self.state.single_version_auto_selected = True
                reply = prefix + f"Only V.{v.get('assigned_version')} of **{resolved_name}** is assigned to you. Would you like to proceed with this version?"
                self.append_assistant_message(reply)
                return reply

            top5 = self.state.version_options_full[:5]
            self.state.version_options = top5
            self.state.awaiting_version_selection = True
            options_list = "\n".join(f"{i+1}. V.{v.get('assigned_version')}" for i, v in enumerate(top5))
            more_line = f"\n{len(top5)+1}. More" if len(self.state.version_options_full) > 5 else ""
            reply = prefix + f"Here are the available versions of **{resolved_name}**:\n\n{options_list}{more_line}\n\nWhich one would you like?"
            self.append_assistant_message(reply)
            return reply

        # not assigned
        details = self.state.resolved_software_details or {}
        all_versions = details.get("versions") or []

        if not all_versions:
            context = prefix + f"**{resolved_name}** is not currently assigned to you, and no versions are available in the catalog."
            return self._offer_ticket_or_show_existing(resolved_name, ticket_kind="no_versions", context_message=context)

        if self.state.request_mode == "update":
            self.state.awaiting_install_from_update_confirmation = True
            self.state.not_assigned_software = resolved_name
            self.state.not_assigned_prefix = prefix
            reply = prefix + f"**{resolved_name}** is not currently installed, and no version is assigned to you. Would you like to install it instead?"
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_notassigned_ticket_intent = True
        self.state.not_assigned_software = resolved_name
        self.state.not_assigned_prefix = prefix

        reply = prefix + f"**{resolved_name}** is not currently assigned to you. Would you like to request a ticket?"
        self.append_assistant_message(reply)
        return reply

        # # not assigned
        # details = self.state.resolved_software_details or {}
        # all_versions = details.get("versions") or []

        # self.state.version_selection_mode = "available"
        # self.state.version_options_full = all_versions

        # if not all_versions:
        #     context = prefix + f"**{resolved_name}** is not currently assigned to you, and no versions are available in the catalog."
        #     return self._offer_ticket_or_show_existing(resolved_name, ticket_kind="no_versions", context_message=context)

        # def _label(v):
        #     base = f"V.{v.get('version')}"
        #     if category == "license":
        #         cost = self._format_cost(v.get("cost"))
        #         base += f" — {cost}"
        #     return base

        # if len(all_versions) == 1:
        #     v = all_versions[0]
        #     self.state.version_options = all_versions
        #     self.state.awaiting_version_selection = True
        #     self.state.single_version_auto_selected = True
        #     reply = prefix + f"**{resolved_name}** is not currently assigned to you. Only {_label(v)} is available. Would you like to proceed with this version?"
        #     self.append_assistant_message(reply)
        #     return reply

        # top5 = all_versions[:5]
        # self.state.version_options = top5
        # self.state.awaiting_version_selection = True

        # version_list = "\n".join(f"{i+1}. {_label(v)}" for i, v in enumerate(top5))
        # more_line = f"\n{len(top5)+1}. More" if len(all_versions) > 5 else ""

        # reply = prefix + f"**{resolved_name}** is not currently assigned to you. Here are the available versions you can request:\n\n{version_list}{more_line}\n\nWhich one would you like?"
        # self.append_assistant_message(reply)
        # return reply


        category = (chosen_version_record.get("category") or "").lower()
        cost = chosen_version_record.get("cost")
        tool_tip = chosen_version_record.get("tool_tip")
        software = self.state.confirmed_software

        if category != "license":
            reply = f"Got it — proceeding with **{software}**. Cost: {cost}. {tool_tip}"
            self.append_assistant_message(reply)
            return reply

        resolution_result = SAMCrew().license_resolution_crew().kickoff(inputs={"software_name": software})
        resolution: SoftwareLicenseResolution = resolution_result.pydantic

        if not resolution.is_microsoft_product:
            return self._check_assignment_and_reply(resolved_name, self.state.selected_serial)

        if not resolution.actual_license_name or not resolution.category:
            reply = f"**{software}** is a Microsoft product, but I couldn't find a matching entry in the license reference table. Escalating for manual review."
            self.append_assistant_message(reply)
            return reply

        ohr_for_check = self.state.target_ohr if self.state.target_ohr else self.state.ohr
        self.state.pending_license_check_category = resolution.category
        self.state.pending_license_name = resolution.actual_license_name

        check_result = SAMCrew().license_check_crew().kickoff(inputs={
            "ohr": ohr_for_check,
            "license_category": resolution.category,
            "license_name": resolution.actual_license_name,
        })
        check: SoftwareLicenseCheckResult = check_result.pydantic

        is_member = "not part of" not in check.response.lower()

        if is_member:
            reply = f"You're part of the **{check.group_name}** group — proceeding with **{software}**."
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_assignment_ticket_confirmation = True
        reply = f"You're not currently part of the **{check.group_name}** group required for **{software}**. Would you like me to raise a request ticket to get access?"
        self.append_assistant_message(reply)
        return reply

    def _format_cost(self, cost) -> str:
        cost_str = str(cost).strip()
        if cost_str.startswith("$"):
            return cost_str
        try:
            return f"${float(cost_str):.2f}"
        except (ValueError, TypeError):
            return f"${cost_str}"

    def _parse_tool_tip(self, tool_tip: str) -> tuple[str, list]:
        """Extracts alternative software names from tool_tip strings formatted as
        'Freeware alternatives available: Name1, Name2'. Returns display names
        (as written) paired with cleaned lookup names (parentheticals stripped)."""
        match = re.search(r"freeware alternatives available:\s*(.+)", tool_tip, re.IGNORECASE)

        if not match:
            return tool_tip.strip(), []

        alt_text = match.group(1)
        raw_names = [a.strip() for a in re.split(r",|\band\b", alt_text) if a.strip()]

        alternatives = []
        for name in raw_names:
            lookup_name = re.sub(r"\s*\([^)]*\)", "", name).strip()  # strip "(...)" for lookup
            alternatives.append({"display": name, "lookup": lookup_name})

        cleaned = tool_tip[:match.start()].strip()
        return cleaned, alternatives

    def _needs_selection_or_confirm(self, versions: list, mode: str, not_assigned_prefix: str = "") -> tuple[bool, str]:
        """Returns (needs_list, reply). If only one version exists, sets up a
        direct confirmation instead of a numbered list."""
        if len(versions) == 1:
            v = versions[0]
            version_label = v.get("version") or v.get("assigned_version")
            self.state.version_selection_mode = mode
            self.state.version_options = versions
            self.state.version_options_full = versions
            self.state.awaiting_version_selection = True
            # mark that this was auto-selected as the only option
            self.state.single_version_auto_selected = True
            reply = f"{not_assigned_prefix}Only V.{version_label} is available. Would you like to proceed with this version?"
            return False, reply
        return True, ""

    def _offer_ticket_or_show_existing(self, software_name: str, ticket_kind: str, context_message: str = "", catalog_sysid: str = "") -> str:
        ohr = self.state.ohr
        onbehalf_ohr = self.state.target_ohr if self.state.target_ohr else None
        nl_context = f"OHR {ohr}" + (f", on behalf of OHR {onbehalf_ohr}" if onbehalf_ohr else "") + f", requesting {software_name}"

        result = SAMCrew().ticket_check_crew().kickoff(inputs={
            "ohr": ohr,
            "onbehalf_ohr": onbehalf_ohr,
            "requested_software_name": software_name,
            "nl_context": nl_context,
            "catalog_sysid": catalog_sysid,
        })
        check: TicketDuplicateCheckResult = result.pydantic

        prefix = f"{context_message}\n\n" if context_message else ""

        if check.duplicate_found and check.matching_tickets:
            t = check.matching_tickets[0]
            self.state.pending_ticket_kind = ticket_kind
            self.state.awaiting_assignment_ticket_confirmation = True
            reply = (
                f"{prefix}You already have an open ticket for **{software_name}**:\n\n"
                f"- RITM: {t.ritm}\n- Status: {t.status}\n- Opened On: {t.opened_on}\n\n"
                f"Would you like to raise a new request anyway?"
            )
            self.append_assistant_message(reply)
            return reply

        self.state.pending_ticket_kind = ticket_kind
        self.state.pending_ticket_flag = check.flag
        self.state.awaiting_assignment_ticket_confirmation = True
        reply = f"{prefix}Would you like me to raise a request ticket for **{software_name}**?"
        self.append_assistant_message(reply)
        return reply

    def _create_ticket_or_show_existing(self, software_name: str, ticket_kind: str, context_message: str = "", catalog_sysid: str = "") -> str:
        ohr = self.state.ohr
        onbehalf_ohr = self.state.target_ohr if self.state.target_ohr else None
        start_date = self.state.ticket_start_date
        end_date = self.state.ticket_end_date

        if onbehalf_ohr:
            who = f"OHR {ohr} is requesting on behalf of OHR {onbehalf_ohr}"
        else:
            who = f"OHR {ohr} is requesting for their own use"

        nl_context = f"{who}. Raise request for {software_name}"
        if start_date and end_date:
            nl_context += f", from {start_date} to {end_date}"
        nl_context += "."

        result = SAMCrew().ticket_check_crew().kickoff(inputs={
            "ohr": ohr,
            "onbehalf_ohr": onbehalf_ohr,
            "requested_software_name": software_name,
            "nl_context": nl_context,
            "catalog_sysid": catalog_sysid,
        })
        check: TicketDuplicateCheckResult = result.pydantic

        if check.duplicate_found and check.matching_tickets:
            t = check.matching_tickets[0]
            reply = (
                f"You already have an open ticket for **{software_name}**:\n\n"
                f"- RITM: {t.ritm}\n- Status: {t.status}\n- Opened On: {t.opened_on}"
            )
            self.append_assistant_message(reply)
            return reply

        flag = check.flag
        reply = flag if flag else f"Sure — raising a request ticket for **{software_name}**."
        self.append_assistant_message(reply)
        return reply

    def _push_install_and_ritm(self, software_name: str, version: str, serial_number: str) -> str:
        ohr_for_push = self.state.target_ohr if self.state.target_ohr else self.state.ohr

        push_result = SAMCrew().push_software_crew().kickoff(inputs={
            "ohr": ohr_for_push, "serial_number": serial_number,
            "software_name": software_name, "version": version,
        })
        push: SoftwarePushResult = push_result.pydantic

        ritm_result = SAMCrew().generate_ritm_crew().kickoff(inputs={
            "ohr": ohr_for_push, "software_name": software_name,
            "version": version, "serial_number": serial_number,
        })
        ritm: RITMGenerationResult = ritm_result.pydantic

        reply = f"**{software_name}** V.{version} is pushed successfully in your system and will be installed shortly.\n\nHere is the ticket number for the software related request: {ritm.ritm_number}"
        self.append_assistant_message(reply)
        return reply





    #Confirmation Handling States
    @listen("confirm_target")
    def handle_confirm_target(self) -> str:
        message = self.state.current_user_message or ""

        decision = self.classify_intent(
            message,
            ("CONFIRMED", "DENIED", "UNCLEAR"),
            llm=llm,
        )

        if decision == "CONFIRMED":
            self.state.awaiting_confirmation = False

            # Only Install currently routes through resolution — other request
            # types (Uninstall/Renew/Transfer/Update) still just echo for now

            if (
                self.state.pending_request_type in ("Install", "Update", "Renew")
                and self.state.pending_software_name
            ):
                self.state.request_mode = {
                    "Install": "install",
                    "Update": "update",
                    "Renew": "renew",
                }[self.state.pending_request_type]

                return self._resolve_software(
                    self.state.pending_software_name
                )


            request_type = self.state.pending_request_type
            software = self.state.pending_software_name
            reply = (
                f"Great, proceeding with the **{request_type}** request"
                + (f" for {software}" if software else "")
                + f" on behalf of **{self.state.target_name}**."
            )
            self.append_assistant_message(reply)
            return reply

        if decision == "DENIED":
            self.state.awaiting_confirmation = False
            self.state.awaiting_target_ohr = True
            self.state.target_ohr = None
            self.state.target_name = None
            reply = "No worries — could you resend the correct 9-digit OHR?"
            self.append_assistant_message(reply)
            return reply

        reply = f"Sorry, just to be clear — is this for **{self.state.target_name}**? (yes/no)"
        self.append_assistant_message(reply)
        return reply

    @listen("confirm_software")
    def handle_confirm_software(self) -> str:
        message = (self.state.current_user_message or "").strip()
        options = self.state.software_candidates

        chosen = None
        if message.isdigit() and 1 <= int(message) <= len(options):
            chosen = options[int(message) - 1]
        else:
            for opt in options:
                if opt.lower() in message.lower() or message.lower() in opt.lower():
                    chosen = opt
                    break

        if not chosen:
            options_list = "\n".join(f"{i+1}. {name}" for i, name in enumerate(options))
            reply = f"Sorry, I didn't catch that. Please pick one:\n\n{options_list}"
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_software_confirmation = False
        self.state.software_candidates = []

        self._fetch_and_store_details(chosen)  

        blacklist_reply = self._check_blacklist_and_reply(chosen)
        if blacklist_reply:
            return blacklist_reply

        return self._after_blacklist_clear(chosen)

    @listen("confirm_blacklist_ticket")
    def handle_confirm_blacklist_ticket(self) -> str:
        message = self.state.current_user_message or ""

        decision = self.classify_intent(
            message,
            ("CONFIRMED", "DENIED", "UNCLEAR"),
            llm=llm,
        )

        if decision == "CONFIRMED":
            self.state.awaiting_blacklist_ticket_confirmation = False
            print("user select Yes")  # TODO: replace with actual ticket creation call later
            reply = "user select Yes"
            self.append_assistant_message(reply)
            return reply

        if decision == "DENIED":
            self.state.awaiting_blacklist_ticket_confirmation = False
            self.state.blacklisted_software_name = None
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        reply = f"Just to confirm — would you like me to raise a ticket for **{self.state.blacklisted_software_name}**? (yes/no)"
        self.append_assistant_message(reply)
        return reply

    @listen("confirm_assignment_ticket")
    def handle_confirm_assignment_ticket(self) -> str:
        message = self.state.current_user_message or ""

        decision = self.classify_intent(
            message,
            ("CONFIRMED", "DENIED", "UNCLEAR"),
            llm=llm,
        )

        if decision == "CONFIRMED":
            self.state.awaiting_assignment_ticket_confirmation = False
            self.state.pending_ticket_kind = None
            flag = self.state.pending_ticket_flag
            self.state.pending_ticket_flag = None

            reply = flag if flag else "Sure — proceeding with your request."
            self.append_assistant_message(reply)
            return reply

        if decision == "DENIED":
            self.state.awaiting_assignment_ticket_confirmation = False
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        reply = "Just to confirm — would you like me to raise a ticket to get this software assigned? (yes/no)"
        self.append_assistant_message(reply)
        return reply

    @listen("confirm_update")
    def handle_confirm_update(self) -> str:
        message = self.state.current_user_message or ""

        decision = self.classify_intent(
            message,
            ("CONFIRMED", "DENIED", "UNCLEAR"),
            llm=llm,
        )

        if decision == "CONFIRMED":
            self.state.awaiting_update_confirmation = False
            not_installed = [
                v for v in self.state.last_assignment_records
                if v.get("assigned_status") and not v.get("installed_status")
            ]
            self.state.installed_versions_for_update = []

            if not_installed:
                self.state.version_selection_mode = "assigned"
                self.state.version_options_full = not_installed
                top5 = not_installed[:5]
                self.state.version_options = top5
                self.state.awaiting_version_selection = True
                self.state.post_version_selection_action = "ticket"

                options_list = "\n".join(f"{i+1}. V.{v.get('assigned_version')}" for i, v in enumerate(top5))
                more_line = f"\n{len(top5)+1}. More" if len(not_installed) > 5 else ""
                reply = f"Here are the available versions of **{self.state.confirmed_software}**:\n\n{options_list}{more_line}\n\nWhich one would you like?"
                self.append_assistant_message(reply)
                return reply

            details = self.state.resolved_software_details or {}
            all_versions = details.get("versions") or []

            self.state.version_selection_mode = "available"
            self.state.version_options_full = all_versions
            top5 = all_versions[:5]
            self.state.version_options = top5
            self.state.awaiting_version_selection = True
            self.state.post_version_selection_action = "ticket"

            if not top5:
                self.state.awaiting_version_selection = False
                self.state.awaiting_assignment_ticket_confirmation = True
                reply = f"No other version of **{self.state.confirmed_software}** is assigned to you, and no versions are available in the catalog. Would you like me to raise a request ticket for it?"
                self.append_assistant_message(reply)
                return reply

            version_list = "\n".join(f"{i+1}. V.{v.get('version')}" for i, v in enumerate(top5))
            more_line = f"\n{len(top5)+1}. More" if len(all_versions) > 5 else ""
            reply = (
                f"No other version of **{self.state.confirmed_software}** is currently assigned to you. "
                f"Here are the available versions:\n\n{version_list}{more_line}\n\nWhich one would you like?"
            )
            self.append_assistant_message(reply)
            return reply
    
        if decision == "DENIED":
            self.state.awaiting_update_confirmation = False
            self.state.installed_versions_for_update = []
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        reply = "Just to confirm — would you like to update the installed version? (yes/no)"
        self.append_assistant_message(reply)
        return reply

    @listen("confirm_cost")
    def handle_confirm_cost(self) -> str:
        message = self.state.current_user_message or ""
        alternatives = self.state.free_alternatives or []
        alt_display_names = [a["display"] for a in alternatives]

        outcomes = ("CONFIRMED", "DENIED") + tuple(alt_display_names) if alt_display_names else ("CONFIRMED", "DENIED", "UNCLEAR")
        decision = self.classify_intent(message, outcomes, llm=llm)

        if decision == "DENIED":
            self.state.awaiting_cost_confirmation = False
            self.state.cost_confirm_version = None
            self.state.free_alternatives = []
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        if decision in alt_display_names:
            chosen_alt = next(a for a in alternatives if a["display"] == decision)
            self.state.awaiting_cost_confirmation = False
            self.state.cost_confirm_version = None
            self.state.free_alternatives = []
            return self._resolve_software(chosen_alt["lookup"])   # restart the pipeline for the alternative

        if decision == "CONFIRMED":
            self.state.awaiting_cost_confirmation = False
            self.state.free_alternatives = []
            self.state.awaiting_duration_input = True
            reply = (
                "Please select the duration for which the software is required.\n\n"
                "Note: The maximum allowable duration is up to 12 months from the start date."
            )
            self.append_assistant_message(reply)
            return reply

        # UNCLEAR
        v = self.state.cost_confirm_version
        cost = self._format_cost(v.get("cost"))
        reply = f"Just to confirm — would you like to proceed at **{cost}**? Or would you prefer one of the free alternatives?"
        self.append_assistant_message(reply)
        return reply

    @listen("collect_duration")
    def handle_collect_duration(self) -> str:
        message = (self.state.current_user_message or "").strip()
        today = date.today()

        try:
            parsed_date = dateutil.parser.parse(message, fuzzy=True, dayfirst=False).date()
        except (ValueError, OverflowError):
            reply = (
                "I couldn't understand that date. Please enter the date you need the "
                "software until (e.g. \"31 Dec 2026\", \"2026-12-31\", or \"in 6 months\")."
            )
            self.append_assistant_message(reply)
            return reply

        max_allowed_date = today + relativedelta(months=12)

        if parsed_date <= today:
            reply = "The date must be in the future. Please enter a valid end date."
            self.append_assistant_message(reply)
            return reply

        if parsed_date > max_allowed_date:
            reply = (
                f"That's beyond the maximum allowed duration. The latest date you can "
                f"select is {max_allowed_date.strftime('%Y-%m-%d')} (12 months from today). "
                f"Please enter a valid date."
            )
            self.append_assistant_message(reply)
            return reply

        self.state.awaiting_duration_input = False
        self.state.ticket_start_date = today.strftime("%Y-%m-%d")
        self.state.ticket_end_date = parsed_date.strftime("%Y-%m-%d")

        chosen = self.state.cost_confirm_version
        version_label = chosen.get("version") if chosen else None
        software = self.state.confirmed_software or self.state.not_assigned_software
        full_name = f"{software} V.{version_label}" if version_label else software
        self.state.cost_confirm_version = None

        return self._create_ticket_or_show_existing(full_name, ticket_kind="version_assignment")

    @listen("confirm_install_from_update")
    def handle_confirm_install_from_update(self) -> str:
        message = self.state.current_user_message or ""
        decision = self.classify_intent(message, ("CONFIRMED", "DENIED", "UNCLEAR"), llm=llm)

        if decision == "DENIED":
            self.state.awaiting_install_from_update_confirmation = False
            reply = "No Problem. Happy to help! Please feel free to reach out whenever you are ready."
            self.append_assistant_message(reply)
            return reply

        if decision == "UNCLEAR":
            reply = f"Just to confirm — would you like to install **{self.state.not_assigned_software}**? (yes/no)"
            self.append_assistant_message(reply)
            return reply

        # CONFIRMED — switch to install mode and continue into the normal not-assigned flow
        self.state.awaiting_install_from_update_confirmation = False
        self.state.request_mode = "install"
        self.state.awaiting_notassigned_ticket_intent = True
        reply = f"Would you like to request a ticket for **{self.state.not_assigned_software}**?"
        self.append_assistant_message(reply)
        return reply


    def _handle_renewal_flow(self, resolved_name: str) -> str:
        """
        Renew flow:

        Renew
          -> Check whether software is assigned/installed
          -> Ask whether user wants renewal request
          -> User confirms
          -> ticket_check_crew()
          -> Return the flag

        No RITM is generated directly here.
        """

        ohr_for_check = (
            self.state.target_ohr
            if self.state.target_ohr
            else self.state.ohr
        )

        result = SAMCrew().assignment_crew().kickoff(
            inputs={
                "ohr": ohr_for_check,
                "serial_number": self.state.selected_serial,
                "software_name": resolved_name,
            }
        )

        assignment: AssignmentCheckResult = result.pydantic

        assigned_records = [
            r for r in assignment.records
            if r.assigned_status
        ]

        installed_records = [
            r for r in assigned_records
            if r.installed_status
        ]

        self.state.renewal_software_name = resolved_name
        self.state.renewal_installed_versions = [
            r.model_dump()
            for r in installed_records
        ]

        # ----------------------------------------------------
        # Already installed
        # ----------------------------------------------------

        if installed_records:
            installed_versions = [
                r.assigned_version
                for r in installed_records
                if r.assigned_version
            ]

            if installed_versions:
                version_text = ", ".join(
                    f"V.{v}"
                    for v in installed_versions
                )

                reply = (
                    f"**{resolved_name}** ({version_text}) "
                    f"is already installed on your system.\n\n"
                    f"Would you like me to raise a renewal request "
                    f"for **{resolved_name}**?"
                )
            else:
                reply = (
                    f"**{resolved_name}** is already installed "
                    f"on your system.\n\n"
                    f"Would you like me to raise a renewal request "
                    f"for **{resolved_name}**?"
                )

            self.state.awaiting_renewal_ticket_confirmation = True

            self.append_assistant_message(reply)
            return reply

        # ----------------------------------------------------
        # Assigned but not installed
        # ----------------------------------------------------

        if assigned_records:
            assigned_versions = [
                r.assigned_version
                for r in assigned_records
                if r.assigned_version
            ]

            if assigned_versions:
                version_text = ", ".join(
                    f"V.{v}"
                    for v in assigned_versions
                )

                reply = (
                    f"**{resolved_name}** is assigned to you "
                    f"({version_text}), but it is not currently "
                    f"installed on the selected device.\n\n"
                    f"Would you like me to raise a renewal request "
                    f"for **{resolved_name}**?"
                )
            else:
                reply = (
                    f"**{resolved_name}** is assigned to you, "
                    f"but it is not currently installed on the "
                    f"selected device.\n\n"
                    f"Would you like me to raise a renewal request "
                    f"for **{resolved_name}**?"
                )

            self.state.awaiting_renewal_ticket_confirmation = True

            self.append_assistant_message(reply)
            return reply

        # ----------------------------------------------------
        # Not assigned and not installed
        # ----------------------------------------------------

        self.state.awaiting_renewal_ticket_confirmation = True

        reply = (
            f"**{resolved_name}** is not currently installed "
            f"or assigned to the selected device.\n\n"
            f"Would you like me to raise a renewal request "
            f"for **{resolved_name}**?"
        )

        self.append_assistant_message(reply)
        return reply


# 7. Add the confirmation listener
# ------------------------------------------------------------

    @listen("confirm_renewal_ticket")
    def handle_confirm_renewal_ticket(self) -> str:

        message = self.state.current_user_message or ""

        decision = self.classify_intent(
            message,
            ("CONFIRMED", "DENIED", "UNCLEAR"),
            llm=llm,
        )

        # ----------------------------------------------------
        # NO
        # ----------------------------------------------------

        if decision == "DENIED":
            self.state.awaiting_renewal_ticket_confirmation = False
            self.state.renewal_installed_versions = []
            self.state.renewal_software_name = None

            reply = (
                "No Problem. Happy to help! "
                "Please feel free to reach out whenever you are ready."
            )

            self.append_assistant_message(reply)
            return reply

        # ----------------------------------------------------
        # UNCLEAR
        # ----------------------------------------------------

        if decision == "UNCLEAR":
            software = self.state.renewal_software_name

            reply = (
                f"Just to confirm — would you like me to raise "
                f"a renewal request for **{software}**? (yes/no)"
            )

            self.append_assistant_message(reply)
            return reply

        # ----------------------------------------------------
        # YES
        # ----------------------------------------------------

        self.state.awaiting_renewal_ticket_confirmation = False

        software = self.state.renewal_software_name

        ohr = self.state.ohr

        onbehalf_ohr = (
            self.state.target_ohr
            if self.state.target_ohr
            else None
        )

        nl_context = (
            f"OHR {ohr} is requesting renewal for "
            f"{software}"
        )

        if onbehalf_ohr:
            nl_context = (
                f"OHR {ohr} is requesting renewal for "
                f"{software} on behalf of OHR {onbehalf_ohr}"
            )

        # ----------------------------------------------------
        # IMPORTANT:
        # Only check/create the flag.
        # Do NOT generate RITM here.
        # ----------------------------------------------------

        result = SAMCrew().ticket_check_crew().kickoff(
            inputs={
                "ohr": ohr,
                "onbehalf_ohr": onbehalf_ohr,
                "requested_software_name": software,
                "nl_context": nl_context,
                "catalog_sysid": "",
            }
        )

        check: TicketDuplicateCheckResult = result.pydantic

        self.state.renewal_installed_versions = []
        self.state.renewal_software_name = None

        # ----------------------------------------------------
        # Existing ticket
        # ----------------------------------------------------

        if check.duplicate_found and check.matching_tickets:
            t = check.matching_tickets[0]

            reply = (
                f"You already have an open renewal request "
                f"for **{software}**:\n\n"
                f"- RITM: {t.ritm}\n"
                f"- Status: {t.status}\n"
                f"- Opened On: {t.opened_on}"
            )

            self.append_assistant_message(reply)
            return reply

        # ----------------------------------------------------
        # Return the flag
        # ----------------------------------------------------

        flag = check.flag

        reply = (
            flag
            if flag
            else f"Renewal request for **{software}** has been submitted."
        )

        self.append_assistant_message(reply)
        return reply


    #Exit Conversation Handler
    @listen("exit_conversation")
    def handle_exit_conversation(self) -> str:
        reply = "Goodbye! Let me know if you need anything else."
        self.append_assistant_message(reply)
        return reply

    


def run_debug():
    flow = SAMFlow()
    print(flow.handle_turn("850081088", session_id="s1"))
    print(flow.handle_turn("install citrix workspace", session_id="s1"))
    print(flow.handle_turn("yes", session_id="s1"))
    print(flow.handle_turn("1", session_id="s1"))
    print(flow.handle_turn("yes", session_id="s1"))

    print(flow.state.resolved_software_details)

def run_chat():
    SAMFlow().chat()


if __name__ == "__main__":
    run_debug()


