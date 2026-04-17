"""
MCP (Model Context Protocol) Client for Scribe AI

Allows connecting to MCP servers to access external tools and data sources.
"""

import json
import subprocess
import threading
import queue
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field
from config import VAULT_PATH


@dataclass
class MCPServer:
    """Represents an MCP server connection."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    tools: List[Dict] = field(default_factory=list)
    resources: List[Dict] = field(default_factory=list)
    connected: bool = False


class MCPClient:
    """Client for managing MCP server connections."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or VAULT_PATH / ".mcp-servers.json"
        self.servers: Dict[str, MCPServer] = {}
        self._load_config()

    def _load_config(self):
        """Load MCP server configurations from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                for name, server_config in config.get("servers", {}).items():
                    self.servers[name] = MCPServer(
                        name=name,
                        command=server_config.get("command", ""),
                        args=server_config.get("args", []),
                        env=server_config.get("env", {})
                    )
            except Exception as e:
                print(f"Error loading MCP config: {e}")

    def _save_config(self):
        """Save MCP server configurations to file."""
        config = {"servers": {}}
        for name, server in self.servers.items():
            config["servers"][name] = {
                "command": server.command,
                "args": server.args,
                "env": server.env
            }
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def add_server(self, name: str, command: str, args: List[str] = None,
                   env: Dict[str, str] = None) -> bool:
        """Add a new MCP server configuration."""
        if name in self.servers:
            return False

        self.servers[name] = MCPServer(
            name=name,
            command=command,
            args=args or [],
            env=env or {}
        )
        self._save_config()
        return True

    def remove_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        if name not in self.servers:
            return False

        self.disconnect(name)
        del self.servers[name]
        self._save_config()
        return True

    def connect(self, name: str) -> bool:
        """Connect to an MCP server."""
        if name not in self.servers:
            return False

        server = self.servers[name]
        if server.connected:
            return True

        try:
            # Start the MCP server process
            env = {**dict(subprocess.os.environ), **server.env}
            server.process = subprocess.Popen(
                [server.command] + server.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )

            # Initialize connection
            self._send_message(server, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "ScribeAI",
                        "version": "1.0.0"
                    }
                }
            })

            response = self._read_message(server)
            if response and "result" in response:
                server.connected = True

                # Get available tools
                self._send_message(server, {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                })
                tools_response = self._read_message(server)
                if tools_response and "result" in tools_response:
                    server.tools = tools_response["result"].get("tools", [])

                # Get available resources
                self._send_message(server, {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/list",
                    "params": {}
                })
                resources_response = self._read_message(server)
                if resources_response and "result" in resources_response:
                    server.resources = resources_response["result"].get("resources", [])

                return True

        except Exception as e:
            print(f"Error connecting to MCP server {name}: {e}")
            self.disconnect(name)

        return False

    def disconnect(self, name: str) -> bool:
        """Disconnect from an MCP server."""
        if name not in self.servers:
            return False

        server = self.servers[name]
        if server.process:
            try:
                server.process.terminate()
                server.process.wait(timeout=5)
            except Exception:
                server.process.kill()
            server.process = None

        server.connected = False
        server.tools = []
        server.resources = []
        return True

    def _send_message(self, server: MCPServer, message: Dict):
        """Send a JSON-RPC message to the server."""
        if not server.process or not server.process.stdin:
            return

        msg_str = json.dumps(message)
        server.process.stdin.write(msg_str + "\n")
        server.process.stdin.flush()

    def _read_message(self, server: MCPServer, timeout: float = 5.0) -> Optional[Dict]:
        """Read a JSON-RPC message from the server."""
        if not server.process or not server.process.stdout:
            return None

        try:
            # Simple blocking read with timeout via select
            import select
            ready, _, _ = select.select([server.process.stdout], [], [], timeout)
            if ready:
                line = server.process.stdout.readline()
                if line:
                    return json.loads(line.strip())
        except Exception as e:
            print(f"Error reading MCP message: {e}")

        return None

    def call_tool(self, server_name: str, tool_name: str,
                  arguments: Dict[str, Any] = None) -> Optional[Dict]:
        """Call a tool on an MCP server."""
        if server_name not in self.servers:
            return None

        server = self.servers[server_name]
        if not server.connected:
            if not self.connect(server_name):
                return None

        self._send_message(server, {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {}
            }
        })

        response = self._read_message(server, timeout=30.0)
        if response and "result" in response:
            return response["result"]

        return None

    def read_resource(self, server_name: str, uri: str) -> Optional[Dict]:
        """Read a resource from an MCP server."""
        if server_name not in self.servers:
            return None

        server = self.servers[server_name]
        if not server.connected:
            if not self.connect(server_name):
                return None

        self._send_message(server, {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "resources/read",
            "params": {"uri": uri}
        })

        response = self._read_message(server, timeout=30.0)
        if response and "result" in response:
            return response["result"]

        return None

    def list_servers(self) -> List[Dict]:
        """List all configured MCP servers with their status."""
        result = []
        for name, server in self.servers.items():
            result.append({
                "name": name,
                "command": server.command,
                "connected": server.connected,
                "tools": [t.get("name", "") for t in server.tools],
                "resources": len(server.resources)
            })
        return result

    def get_all_tools(self) -> List[Dict]:
        """Get all tools from all connected servers."""
        tools = []
        for name, server in self.servers.items():
            if server.connected:
                for tool in server.tools:
                    tools.append({
                        **tool,
                        "server": name
                    })
        return tools

    def get_all_resources(self) -> List[Dict]:
        """Get all resources from all connected servers."""
        resources = []
        for name, server in self.servers.items():
            if server.connected:
                for resource in server.resources:
                    resources.append({
                        **resource,
                        "server": name
                    })
        return resources


# Global MCP client instance
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client
