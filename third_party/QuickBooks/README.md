# QuickBooks Online MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that connects Claude to QuickBooks Online, giving Claude direct access to your accounting data — customers, invoices, items, payments, accounts, and reports.

## Prerequisites

- Python 3.10+
- A [QuickBooks Online developer account](https://developer.intuit.com)
- An Intuit app with OAuth 2.0 credentials

## Setup

### 1. Install dependencies

```bash
cd third_party/QuickBooks
pip install -r requirements.txt
```

### 2. Create your Intuit app

1. Go to https://developer.intuit.com and sign in
2. Create a new app → select **QuickBooks Online and Payments**
3. Note your **Client ID** and **Client Secret** from the app's Keys & credentials page

### 3. Get OAuth tokens

1. Visit the [Intuit OAuth 2.0 Playground](https://developer.intuit.com/app/developer/playground)
2. Select your app and the scopes you need (`com.intuit.quickbooks.accounting`)
3. Complete the authorization flow to get a **refresh token**
4. Note your **Company ID** (realm ID) from the playground URL

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
QB_CLIENT_ID=ABcDeFgHiJkLmNoPqRsTuVwXyZ
QB_CLIENT_SECRET=aBcDeFgHiJkLmNoPqRsTuV
QB_REFRESH_TOKEN=AB11234567890abcdef
QB_COMPANY_ID=1234567890
QB_ENVIRONMENT=sandbox
```

### 5. Connect to Claude

Add the server to your Claude Code MCP configuration (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "python",
      "args": ["/path/to/third_party/QuickBooks/quickbooks_mcp_server.py"],
      "env": {
        "QB_CLIENT_ID": "your_client_id",
        "QB_CLIENT_SECRET": "your_client_secret",
        "QB_REFRESH_TOKEN": "your_refresh_token",
        "QB_COMPANY_ID": "your_company_id",
        "QB_ENVIRONMENT": "sandbox"
      }
    }
  }
}
```

Or, if using a `.env` file, point to the directory:

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "python",
      "args": ["/path/to/third_party/QuickBooks/quickbooks_mcp_server.py"],
      "cwd": "/path/to/third_party/QuickBooks"
    }
  }
}
```

## Available tools

### Customers
| Tool | Description |
|------|-------------|
| `list_customers` | List all customers |
| `get_customer` | Get a customer by ID |
| `create_customer` | Create a new customer |

### Invoices
| Tool | Description |
|------|-------------|
| `list_invoices` | List all invoices |
| `get_invoice` | Get an invoice by ID |
| `create_invoice` | Create a new invoice with line items |
| `send_invoice` | Email an invoice to the customer |

### Items (Products & Services)
| Tool | Description |
|------|-------------|
| `list_items` | List all items |
| `get_item` | Get an item by ID |
| `create_item` | Create a new product or service |

### Payments
| Tool | Description |
|------|-------------|
| `list_payments` | List all payments |
| `get_payment` | Get a payment by ID |
| `create_payment` | Record a payment (optionally linked to an invoice) |

### Accounts
| Tool | Description |
|------|-------------|
| `list_accounts` | List the Chart of Accounts |
| `get_account` | Get an account by ID |

### Reports
| Tool | Description |
|------|-------------|
| `get_profit_and_loss` | Profit & Loss report (with optional date range) |
| `get_balance_sheet` | Balance Sheet report (with optional date range) |

### Query
| Tool | Description |
|------|-------------|
| `run_query` | Run a raw QuickBooks SQL-like query for flexible lookups |

## Example prompts

Once connected, you can ask Claude things like:

- *"List all my customers in QuickBooks"*
- *"Create an invoice for customer 5 with 3 hours of consulting at $150/hr"*
- *"Show me the profit and loss report for Q1 2025"*
- *"Find all invoices over $1,000"* (uses `run_query`)
- *"Record a $500 payment from customer 12 against invoice 42"*

## Architecture

```
quickbooks_auth.py      — OAuth2 token management (auto-refresh)
quickbooks_mcp_server.py — MCP server with tool definitions
.env.example            — Template for environment variables
```

The server uses the [FastMCP](https://github.com/modelcontextprotocol/python-sdk) framework. Each tool maps to a QuickBooks Online API endpoint. Authentication is handled transparently — the auth module refreshes expired tokens automatically.

## Switching to production

1. Change `QB_ENVIRONMENT=production` in your `.env`
2. Use production OAuth credentials (not sandbox)
3. Ensure your Intuit app has been reviewed/published if needed
