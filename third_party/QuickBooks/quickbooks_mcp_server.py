"""
QuickBooks Online MCP Server

An MCP (Model Context Protocol) server that exposes QuickBooks Online
accounting data to Claude. Supports reading and writing customers,
invoices, items, payments, and accounts, plus a flexible query tool.

Usage:
    python quickbooks_mcp_server.py

Environment variables (or .env file):
    QB_CLIENT_ID       - Intuit OAuth2 client ID
    QB_CLIENT_SECRET   - Intuit OAuth2 client secret
    QB_REFRESH_TOKEN   - OAuth2 refresh token
    QB_COMPANY_ID      - QuickBooks company (realm) ID
    QB_ENVIRONMENT     - "sandbox" or "production" (default: sandbox)
"""

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from quickbooks_auth import QuickBooksAuth

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QB_ENVIRONMENT = os.environ.get("QB_ENVIRONMENT", "sandbox").lower()
QB_COMPANY_ID = os.environ.get("QB_COMPANY_ID", "")

BASE_URLS = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
    "production": "https://quickbooks.api.intuit.com",
}

BASE_URL = BASE_URLS.get(QB_ENVIRONMENT, BASE_URLS["sandbox"])

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "QuickBooks Online",
    description="Connect Claude to QuickBooks Online for accounting operations",
)

auth = QuickBooksAuth.from_env()
http_client = httpx.AsyncClient(timeout=30.0)


async def _qb_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated request to the QuickBooks Online API."""
    if not QB_COMPANY_ID:
        raise ValueError("QB_COMPANY_ID environment variable is required.")

    token = await auth.get_access_token()
    url = f"{BASE_URL}/v3/company/{QB_COMPANY_ID}/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    resp = await http_client.request(
        method, url, headers=headers, params=params, json=json_body
    )
    resp.raise_for_status()
    return resp.json()


async def _qb_query(query: str) -> list[dict[str, Any]]:
    """Run a QuickBooks query and return the result rows."""
    data = await _qb_request("GET", "query", params={"query": query})
    response = data.get("QueryResponse", {})
    # The key for the entity list varies; grab the first list we find.
    for value in response.values():
        if isinstance(value, list):
            return value
    return []


# ---------------------------------------------------------------------------
# Tools — Customers
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_customers(max_results: int = 100) -> str:
    """List customers from QuickBooks Online.

    Args:
        max_results: Maximum number of customers to return (default 100).
    """
    rows = await _qb_query(
        f"SELECT * FROM Customer MAXRESULTS {max_results}"
    )
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_customer(customer_id: str) -> str:
    """Get a single customer by ID.

    Args:
        customer_id: The QuickBooks customer ID.
    """
    data = await _qb_request("GET", f"customer/{customer_id}")
    return json.dumps(data.get("Customer", data), indent=2)


@mcp.tool()
async def create_customer(
    display_name: str,
    email: str = "",
    phone: str = "",
    company_name: str = "",
) -> str:
    """Create a new customer in QuickBooks Online.

    Args:
        display_name: The display name for the customer (required).
        email: Primary email address.
        phone: Primary phone number.
        company_name: Company name.
    """
    body: dict[str, Any] = {"DisplayName": display_name}
    if email:
        body["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        body["PrimaryPhone"] = {"FreeFormNumber": phone}
    if company_name:
        body["CompanyName"] = company_name

    data = await _qb_request("POST", "customer", json_body=body)
    return json.dumps(data.get("Customer", data), indent=2)


# ---------------------------------------------------------------------------
# Tools — Invoices
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_invoices(max_results: int = 100) -> str:
    """List invoices from QuickBooks Online.

    Args:
        max_results: Maximum number of invoices to return (default 100).
    """
    rows = await _qb_query(
        f"SELECT * FROM Invoice MAXRESULTS {max_results}"
    )
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_invoice(invoice_id: str) -> str:
    """Get a single invoice by ID.

    Args:
        invoice_id: The QuickBooks invoice ID.
    """
    data = await _qb_request("GET", f"invoice/{invoice_id}")
    return json.dumps(data.get("Invoice", data), indent=2)


@mcp.tool()
async def create_invoice(
    customer_id: str,
    line_items: list[dict[str, Any]],
    due_date: str = "",
) -> str:
    """Create a new invoice in QuickBooks Online.

    Args:
        customer_id: The QuickBooks customer ID to bill.
        line_items: List of line item dicts, each with:
            - "Description": str
            - "Amount": float
            - "DetailType": "SalesItemLineDetail" (default)
            - "SalesItemLineDetail": {"ItemRef": {"value": "<item_id>"}, "Qty": int, "UnitPrice": float}
        due_date: Due date in YYYY-MM-DD format (optional).

    Example line_items:
        [
            {
                "Amount": 150.00,
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": "1"},
                    "Qty": 3,
                    "UnitPrice": 50.00
                },
                "Description": "Consulting hours"
            }
        ]
    """
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "Line": line_items,
    }
    if due_date:
        body["DueDate"] = due_date

    data = await _qb_request("POST", "invoice", json_body=body)
    return json.dumps(data.get("Invoice", data), indent=2)


@mcp.tool()
async def send_invoice(invoice_id: str, email: str = "") -> str:
    """Email an invoice to the customer.

    Args:
        invoice_id: The QuickBooks invoice ID.
        email: Override email address (uses customer email if blank).
    """
    params = {}
    if email:
        params["sendTo"] = email
    data = await _qb_request(
        "POST", f"invoice/{invoice_id}/send", params=params
    )
    return json.dumps(data.get("Invoice", data), indent=2)


# ---------------------------------------------------------------------------
# Tools — Items (Products / Services)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_items(max_results: int = 100) -> str:
    """List items (products and services) from QuickBooks Online.

    Args:
        max_results: Maximum number of items to return (default 100).
    """
    rows = await _qb_query(
        f"SELECT * FROM Item MAXRESULTS {max_results}"
    )
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_item(item_id: str) -> str:
    """Get a single item by ID.

    Args:
        item_id: The QuickBooks item ID.
    """
    data = await _qb_request("GET", f"item/{item_id}")
    return json.dumps(data.get("Item", data), indent=2)


@mcp.tool()
async def create_item(
    name: str,
    item_type: str = "Service",
    unit_price: float = 0.0,
    income_account_id: str = "1",
) -> str:
    """Create a new item (product or service) in QuickBooks Online.

    Args:
        name: The item name.
        item_type: "Service" or "Inventory" (default: Service).
        unit_price: Unit price for the item.
        income_account_id: The income account ID to post revenue to.
    """
    body: dict[str, Any] = {
        "Name": name,
        "Type": item_type,
        "UnitPrice": unit_price,
        "IncomeAccountRef": {"value": income_account_id},
    }
    data = await _qb_request("POST", "item", json_body=body)
    return json.dumps(data.get("Item", data), indent=2)


# ---------------------------------------------------------------------------
# Tools — Payments
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_payments(max_results: int = 100) -> str:
    """List payments from QuickBooks Online.

    Args:
        max_results: Maximum number of payments to return (default 100).
    """
    rows = await _qb_query(
        f"SELECT * FROM Payment MAXRESULTS {max_results}"
    )
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_payment(payment_id: str) -> str:
    """Get a single payment by ID.

    Args:
        payment_id: The QuickBooks payment ID.
    """
    data = await _qb_request("GET", f"payment/{payment_id}")
    return json.dumps(data.get("Payment", data), indent=2)


@mcp.tool()
async def create_payment(
    customer_id: str,
    total_amount: float,
    invoice_id: str = "",
) -> str:
    """Record a payment in QuickBooks Online.

    Args:
        customer_id: The customer making the payment.
        total_amount: Payment amount.
        invoice_id: Invoice to apply the payment to (optional).
    """
    body: dict[str, Any] = {
        "CustomerRef": {"value": customer_id},
        "TotalAmt": total_amount,
    }
    if invoice_id:
        body["Line"] = [
            {
                "Amount": total_amount,
                "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
            }
        ]

    data = await _qb_request("POST", "payment", json_body=body)
    return json.dumps(data.get("Payment", data), indent=2)


# ---------------------------------------------------------------------------
# Tools — Accounts (Chart of Accounts)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_accounts(max_results: int = 100) -> str:
    """List accounts from the Chart of Accounts.

    Args:
        max_results: Maximum number of accounts to return (default 100).
    """
    rows = await _qb_query(
        f"SELECT * FROM Account MAXRESULTS {max_results}"
    )
    return json.dumps(rows, indent=2)


@mcp.tool()
async def get_account(account_id: str) -> str:
    """Get a single account by ID.

    Args:
        account_id: The QuickBooks account ID.
    """
    data = await _qb_request("GET", f"account/{account_id}")
    return json.dumps(data.get("Account", data), indent=2)


# ---------------------------------------------------------------------------
# Tools — Reports
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_profit_and_loss(
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Get a Profit and Loss report.

    Args:
        start_date: Start date in YYYY-MM-DD format (optional).
        end_date: End date in YYYY-MM-DD format (optional).
    """
    params: dict[str, str] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    data = await _qb_request("GET", "reports/ProfitAndLoss", params=params)
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_balance_sheet(
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Get a Balance Sheet report.

    Args:
        start_date: Start date in YYYY-MM-DD format (optional).
        end_date: End date in YYYY-MM-DD format (optional).
    """
    params: dict[str, str] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    data = await _qb_request("GET", "reports/BalanceSheet", params=params)
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tools — Generic Query
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_query(query: str) -> str:
    """Run a raw QuickBooks query (SQL-like syntax).

    Use this for flexible queries that the other tools don't cover.
    QuickBooks uses a SQL-like query language.

    Args:
        query: A QuickBooks query string.

    Examples:
        "SELECT * FROM Customer WHERE DisplayName LIKE '%Acme%'"
        "SELECT * FROM Invoice WHERE TotalAmt > '1000.00'"
        "SELECT * FROM Bill WHERE DueDate < '2025-12-31'"
        "SELECT * FROM Vendor MAXRESULTS 50"
    """
    rows = await _qb_query(query)
    return json.dumps(rows, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
