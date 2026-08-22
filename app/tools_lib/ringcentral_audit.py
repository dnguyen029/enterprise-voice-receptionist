import base64
import os
import time
from datetime import UTC, datetime, timedelta

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

client_id = os.getenv("RINGCENTRAL_CLIENT_ID")
client_secret = os.getenv("RINGCENTRAL_CLIENT_SECRET")
jwt = os.getenv("RINGCENTRAL_JWT")
server_url = os.getenv("RINGCENTRAL_SERVER_URL") or "https://platform.ringcentral.com"

if not client_id or not client_secret or not jwt:
    print("Error: RingCentral credentials missing in env.")
    exit(1)


def get_access_token():
    auth_str = f"{client_id}:{client_secret}"
    auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    token_url = f"{server_url}/restapi/oauth/token"
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }
    r = requests.post(token_url, headers=headers, data=data)
    r.raise_for_status()
    return r.json().get("access_token")


def get_user_extensions(access_token):
    url = f"{server_url}/restapi/v1.0/account/~/extension"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    params = {"perPage": 1000}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    records = r.json().get("records", [])
    return [rec for rec in records if rec.get("type") == "User"]


def get_call_logs(access_token, date_from_str):
    url = f"{server_url}/restapi/v1.0/account/~/call-log"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    params = {"dateFrom": date_from_str, "perPage": 1000, "view": "Simple"}
    calls = []
    page = 1
    while url:
        params["page"] = page
        try:
            r = requests.get(url, headers=headers, params=params)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                print(f"Rate limited (429). Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            data = r.json()
            records = data.get("records", [])
            calls.extend(records)
            print(f"Retrieved page {page} ({len(records)} records)")

            navigation = data.get("navigation", {})
            if navigation.get("nextPage") and len(records) == 1000:
                page += 1
                time.sleep(0.5)  # Small pause to avoid hitting rate limits
            else:
                break
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
    return calls


def audit():
    token = get_access_token()
    extensions = get_user_extensions(token)

    # 90 days ago ISO format
    now = datetime.now(UTC)
    date_from = now - timedelta(days=90)
    date_from_str = date_from.isoformat()

    print(f"Fetching call logs since: {date_from_str}...")
    calls = get_call_logs(token, date_from_str)
    print(f"Total call log records retrieved: {len(calls)}")

    # Track calls per extension number and ID
    call_counts = {str(ext.get("extensionNumber")): 0 for ext in extensions}
    call_counts_by_id = {str(ext.get("id")): 0 for ext in extensions}

    for call in calls:
        # Check from
        from_info = call.get("from", {})
        from_ext = from_info.get("extensionNumber")
        from_id = from_info.get("extensionId")
        if from_ext and str(from_ext) in call_counts:
            call_counts[str(from_ext)] += 1
        if from_id and str(from_id) in call_counts_by_id:
            call_counts_by_id[str(from_id)] += 1

        # Check to
        to_info = call.get("to", {})
        to_ext = to_info.get("extensionNumber")
        to_id = to_info.get("extensionId")
        if to_ext and str(to_ext) in call_counts:
            call_counts[str(to_ext)] += 1
        if to_id and str(to_id) in call_counts_by_id:
            call_counts_by_id[str(to_id)] += 1

    report_lines = []
    report_lines.append("# RingCentral Inactive Extensions Audit Report")
    report_lines.append(f"Generated at: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report_lines.append(
        f"Call log audit window: 90 days (since {date_from.strftime('%Y-%m-%d')})\n"
    )
    report_lines.append(
        "| Name | Extension | Status | Call Count (90d) | Recommendation |"
    )
    report_lines.append("| :--- | :--- | :--- | :--- | :--- |")

    for ext in extensions:
        name = (
            ext.get("contact", {}).get("firstName", "")
            + " "
            + ext.get("contact", {}).get("lastName", "")
        )
        name = name.strip() or "Unnamed Extension"
        ext_num = str(ext.get("extensionNumber"))
        ext_id = str(ext.get("id"))
        status = ext.get("status")

        # Max of call count by extension number or ID
        total_calls = max(call_counts.get(ext_num, 0), call_counts_by_id.get(ext_id, 0))

        recommendation = "Keep Seat"
        if status != "Enabled":
            recommendation = f"**Release Seat** (Extension {status})"
        elif total_calls == 0:
            recommendation = "**Release Seat / Deactivate** (0 calls in 90 days)"
        elif total_calls < 5:
            recommendation = "Monitor (Underutilized: < 5 calls in 90 days)"

        report_lines.append(
            f"| {name} | {ext_num} | {status} | {total_calls} | {recommendation} |"
        )

    report = "\n".join(report_lines)

    report_dir = "/home/dnguyen029/.gemini/antigravity-ide/brain/5999b58f-e9a6-45d4-b8ed-260e828c6d2c"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "ringcentral_audit_report.md")
    with open(report_path, "w") as f:
        f.write(report)

    print(f"Audit completed successfully. Report saved to: {report_path}")


if __name__ == "__main__":
    audit()
