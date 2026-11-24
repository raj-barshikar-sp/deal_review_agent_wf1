"""Check the SharePoint connection: resolve the site/drive, create the month folder, upload a note.

    python -m scripts.sharepoint_smoke "Test Customer"
"""

import sys
from datetime import date

from app.core.env import load_env
from app.integrations import sharepoint
from app.integrations.sharepoint.client import root_path, root_segments


def main() -> None:
    load_env()
    customer = sys.argv[1] if len(sys.argv) > 1 else "Test Customer"
    segments = sharepoint.folder_segments(root_path(), customer, date.today())
    print("Folder:", "/".join(segments))
    print("Folder URL:", sharepoint.ensure_folder(segments, existing=len(root_segments())))
    print("File URL:", sharepoint.upload_file(segments, "smoke-test.txt", b"deal review agent smoke test\n"))


if __name__ == "__main__":
    main()
