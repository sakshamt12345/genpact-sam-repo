from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    request_for: Literal["self", "someone_else"] = Field(..., description="Whether the request is for the employee themselves or on behalf of someone else")
    on_behalf_of: Optional[str] = Field(None, description="Name of the other person, only if request_for is 'someone_else'")
    request_type: Literal["Install", "Uninstall", "Renew", "Transfer", "Update", "General Query"] = Field(..., description="The category of the request")
    software_name: Optional[str] = Field(None, description="Name of the software involved, if mentioned")
    summary: str = Field(..., description="One-line summary of what the user is asking for")

class SoftwareCandidate(BaseModel):
    unique_name: str = Field(..., description="The unique product name (not a specific version/build)")
    reasoning: str = Field(..., description="Why this is treated as a distinct product matching the user's input")

class SoftwareResolution(BaseModel):
    matched_software: Optional[str] = Field(None, description="The single unique product name, ONLY if there is exactly one confident, unambiguous match")
    candidates: List[SoftwareCandidate] = Field(default_factory=list,description="If the user's input could refer to more than one DISTINCT product, list each unique product once here with reasoning. Leave empty if matched_software is set.")
    confidence: str = Field(..., description="One of: 'high' (single clear match), 'ambiguous' (multiple distinct products), 'none' (no match)")
    reasoning: str = Field(..., description="Overall explanation of the resolution decision")

class SoftwareVersionDetail(BaseModel):
    software_name: str
    version: str
    cost: str
    tool_tip: str
    blacklisted: bool
    active: bool
    category: str

class SoftwareDetailsResult(BaseModel):
    software_name: str = Field(..., description="The resolved software name these details belong to")
    versions: List[SoftwareVersionDetail] = Field(default_factory=list)

class DeviceInfo(BaseModel):
    status: str
    serial_number: str
    model: str
    last_seen: str

class DeviceLookupResult(BaseModel):
    ohr: int
    devices: List[DeviceInfo] = []

class AssignmentRecord(BaseModel):
    name: str
    display_name: str
    assigned_status: bool
    assigned_version: Optional[str] = None
    installed_status: bool
    installed_version: Optional[str] = None
    meta: Dict[str, Any] = {}

class AssignmentCheckResult(BaseModel):
    software_name: str
    records: List[AssignmentRecord] = []

class SoftwareLicenseResolution(BaseModel):
    is_microsoft_product: bool
    actual_license_name: Optional[str] = None
    category: Optional[Literal["software_license_check", "deny_group_check"]] = None
    reasoning: str

class SoftwareLicenseCheckResult(BaseModel):
    response: str   
    group_name: str

class TicketInfo(BaseModel):
    ritm: str
    status: str
    software: str
    opened_on: str

class TicketLookupResult(BaseModel):
    ohr: int
    onbehalf_ohr: Optional[int] = None
    has_active_ticket: bool
    tickets: List[TicketInfo] = []

class TicketDuplicateCheckResult(BaseModel):
    requested_software_name: str
    duplicate_found: bool
    matching_tickets: List[TicketInfo] = []
    flag: Optional[str] = None

class SoftwarePushResult(BaseModel):
    software_name: str
    version: str
    serial_number: str
    success: bool

class RITMGenerationResult(BaseModel):
    software_name: str
    version: str
    ritm_number: str