from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


ROOT = Path(__file__).resolve().parent
CLIENT_FILE = ROOT / "gmail-oauth-client.json"
TOKEN_FILE = ROOT / "gmail-oauth-token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> None:
    if not CLIENT_FILE.exists():
        raise SystemExit(f"找不到 OAuth 憑證：{CLIENT_FILE}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    print("Gmail OAuth 授權完成。")


if __name__ == "__main__":
    main()
