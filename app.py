import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from msal import ConfidentialClientApplication
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))

# Azure SQL config
db_server = os.environ.get("AZURE_SQL_SERVER")
db_database = os.environ.get("AZURE_SQL_DATABASE")
db_username = os.environ.get("AZURE_SQL_USERNAME")
db_password = os.environ.get("AZURE_SQL_PASSWORD")
driver = "{ODBC Driver 18 for SQL Server}"
connection_string = f"mssql+pyodbc://{db_username}:{db_password}@{db_server}:1433/{db_database}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&Connection Timeout=30"

app.config["SQLALCHEMY_DATABASE_URI"] = connection_string
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# MSAL Config (Microsoft Entra)
CLIENT_ID = os.environ.get("AZURE_AD_CLIENT_ID")
CLIENT_SECRET = os.environ.get("AZURE_AD_CLIENT_SECRET")
TENANT_ID = os.environ.get("AZURE_AD_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = "/getAToken"
SCOPE = ["User.Read"]

msal_app = ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

# Example Model: Edit this for your table's columns
class SampleTable(db.Model):
    __tablename__ = "SampleTable"  # Change to your table name
    id = db.Column(db.Integer, primary_key=True)
    col1 = db.Column(db.String(100))
    col2 = db.Column(db.String(100))

# Middleware for reverse proxy setups (e.g., Azure App Service)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def is_logged_in():
    return "user" in session

@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))
    records = SampleTable.query.all()
    return render_template("table_edit.html", records=records)

@app.route("/edit/<int:row_id>", methods=["POST"])
def edit_row(row_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    row = SampleTable.query.get_or_404(row_id)
    # Update columns based on your table
    row.col1 = request.form.get("col1")
    row.col2 = request.form.get("col2")
    db.session.commit()
    return redirect(url_for("index"))

@app.route("/login")
def login():
    # Microsoft Entra SSO
    state = str(uuid.uuid4())
    session["state"] = state
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        state=state,
        redirect_uri=url_for("authorized", _external=True),
    )
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():
    if request.args.get("state") != session.get("state"):
        return redirect(url_for("index"))  # Invalid state
    code = request.args.get("code")
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=url_for("authorized", _external=True),
    )
    if "id_token_claims" in result:
        session["user"] = result["id_token_claims"]
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={url_for('index', _external=True)}"
    )

if __name__ == "__main__":
    app.run(debug=True)