import base64
import os
from datetime import UTC, datetime

import requests

# Load env variables manually
env_path = "/home/dnguyen029/antigravity-project/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

subdomain = os.getenv("ZENDESK_SUBDOMAIN")
email = os.getenv("ZENDESK_EMAIL")
token = os.getenv("ZENDESK_TOKEN") or os.getenv("ZENDESK_API_KEY")

if not subdomain or not email or not token:
    print("Error: Zendesk credentials missing in env.")
    exit(1)

formatted_email = email if email.endswith("/token") else f"{email}/token"
auth_str = f"{formatted_email}:{token}"
auth_bytes = auth_str.encode("utf-8")
auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
headers = {"Authorization": f"Basic {auth_b64}", "Accept": "application/json"}

base_url = f"https://{subdomain}.zendesk.com/api/v2"


def get_staff_users():
    staff = []
    for role in ["agent", "admin"]:
        url = f"{base_url}/users.json?role={role}"
        while url:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            staff.extend(data.get("users", []))
            url = data.get("next_page")
    return staff


def audit():
    users = get_staff_users()
    now = datetime.now(UTC)

    report_lines = []
    report_lines.append("# Zendesk Inactive Seats Audit Report")
    report_lines.append(f"Generated at: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    report_lines.append(
        "| Name | Email | Role | Active | Suspended | Last Login | Days Inactive | Recommendation |"
    )
    report_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for u in users:
        name = u.get("name")
        email = u.get("email")
        role = u.get("role")
        active = u.get("active")
        suspended = u.get("suspended")
        last_login_str = u.get("last_login_at")

        days_inactive = "Never logged in"
        recommendation = "Keep Seat"

        if last_login_str:
            last_login = datetime.strptime(
                last_login_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=UTC)
            delta = now - last_login
            days = delta.days
            days_inactive = str(days)

            if days > 90:
                recommendation = "**Deactivate / Downgrade** (Inactive > 90 days)"
            elif days > 60:
                recommendation = "**Downgrade to Light Agent** (Inactive > 60 days)"
            elif days > 30:
                recommendation = "Monitor (Inactive > 30 days)"
        else:
            created_at_str = u.get("created_at")
            if created_at_str:
                created_at = datetime.strptime(
                    created_at_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC)
                created_days = (now - created_at).days
                if created_days > 14:
                    recommendation = (
                        "**Deactivate / Downgrade** (Never logged in, > 14 days old)"
                    )
                else:
                    recommendation = "New Account (Verify)"
            else:
                recommendation = "**Deactivate / Downgrade** (Never logged in)"

        if suspended:
            recommendation = "**Release Seat** (Suspended Agent)"

        report_lines.append(
            f"| {name} | {email} | {role} | {active} | {suspended} | {last_login_str or 'Never'} | {days_inactive} | {recommendation} |"
        )

    report = "\n".join(report_lines)

    report_dir = "/home/dnguyen029/.gemini/antigravity-ide/brain/5999b58f-e9a6-45d4-b8ed-260e828c6d2c"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "zendesk_audit_report.md")
    with open(report_path, "w") as f:
        f.write(report)

    print(f"Audit completed successfully. Report saved to: {report_path}")


if __name__ == "__main__":
    audit()
