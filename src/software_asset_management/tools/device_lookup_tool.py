import json
from typing import Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import os


class DeviceLookupInput(BaseModel):
    ohr: int = Field(
        ...,
        description="The OHR of the employee (self or on-behalf-of) to fetch devices for"
    )


class DeviceLookupTool(BaseTool):
    name: str = "Device Lookup"
    description: str = (
        "Given an employee's OHR, fetches all devices registered/assigned to them "
        "from Workspace ONE AirWatch, including serial number, model, device ID, "
        "UUID, and last seen information."
    )
    args_schema: Type[BaseModel] = DeviceLookupInput

    def _run(self, ohr: int) -> str:
        try:
            token_url = "https://apac.uemauth.workspaceone.com/connect/token"

            client_id = os.environ["AIRWATCH_CLIENT_ID"]
            client_secret = os.environ["AIRWATCH_CLIENT_SECRET"]

            token_data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }

            token_response = requests.post(
                token_url,
                data=token_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30,
            )

            token_response.raise_for_status()

            token_json = token_response.json()
            access_token = token_json.get("access_token")

            if not access_token:
                raise Exception(
                    "AirWatch Auth Failed: No access token received."
                )


            search_url = (
                "https://as1106.awmdm.com/API/mdm/devices/search"
            )

            search_response = requests.get(
                search_url,
                params={"user": str(ohr)},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )

            if search_response.status_code == 204:
                return json.dumps({
                    "status": "macbook_detected",
                    "message": (
                        "MacBook detected. Automated remediation is not "
                        "supported for macOS devices at this time."
                    )
                })

            search_response.raise_for_status()


            search_data = search_response.json()

            devices = search_data.get("Devices", [])

            if not devices:
                return json.dumps({
                    "status": "no_devices",
                    "message": "No managed devices found for this user."
                })


            device_list = []

            for device in devices:
                device_id = device.get("Id")

                if isinstance(device_id, dict):
                    device_id = device_id.get("Value")

                device_list.append({
                    "serial_number": device.get("SerialNumber"),
                    "model": device.get("Model"),
                    "device_id": device_id,
                    "uuid": device.get("Uuid"),
                    "last_seen": device.get("LastSeen"),
                })


            return json.dumps({
                "status": "success",
                "count": len(device_list),
                "devices": device_list,
            }, indent=2)

        except requests.exceptions.RequestException as error:
            return json.dumps({
                "status": "error",
                "message": str(error),
            })

        except Exception as error:
            return json.dumps({
                "status": "error",
                "message": str(error),
            })
