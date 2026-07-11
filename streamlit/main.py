import streamlit.web.cli as stcli
import sys
import os

if __name__ == "__main__":
    base_path = getattr(
        sys,
        "_MEIPASS",
        os.path.dirname(os.path.abspath(__file__)),
    )
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(base_path, "app.py")

    if not os.path.exists(app_path):
        sys.exit(1)

    sys.argv = ["streamlit", "run", app_path, "--global.developmentMode=false"]
    sys.exit(stcli.main())
