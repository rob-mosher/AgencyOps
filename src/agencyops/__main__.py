"""Entry point: python -m agencyops"""

from agencyops.mcp_server import mcp


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
