"""
utils.py

Contains validation utilities, type adapaters for argparse, configuration resolvers, 
and helper functions for rule generation and SID management in Snortsmith
"""

import ipaddress
import argparse
import re
import os

from snortsmith_rulegen._config import _get_config_value


def _validate_protocol(value: str) -> str:
    """Validate protocol for Snort rules (tcp, udp, icmp, ip)"""
    allowed = {"tcp", "udp", "icmp", "ip"}
    val = value.lower()
    if val in allowed:
        return val
    raise ValueError(f"Invalid protocol: '{value}'. Must be one of {', '.join(allowed)}.")


def _validate_ip(value: str) -> str:
    """Validate IP address or allow 'any' and Snort-style vars like $HOME_NET."""
    if value.lower() == "any" or value.startswith("$"):
        return value
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        raise ValueError(f"Invalid IP address: {value}")
    

def _validate_port(value: str) -> str:
    """Validate port number or allow 'any'."""
    if value.lower() == "any":
        return "any"
    try:
        port = int(value)
        if 0 <= port <= 65535:
            return str(port)
        else:
            raise ValueError("Port must be between 0 and 65535.")
    except ValueError:
        raise ValueError("Invalid port: must be an integer or 'any'.")
    

def _validate_priority(value: str) -> str:
    """Validate Snort priority (1 - 2,147,483,647)."""
    try:
        priority = int(value)
        if 1 <= priority <= 2_147_483_647:
            return str(priority)
        raise ValueError("Priority must be between 1 and 2,147,483,647.")
    except ValueError:
        raise ValueError("Invalid priority: must be an integer.")
    

def _validate_offset_depth(offset: str | None, depth: str | None) -> tuple[int | None, int | None]:
    """
    Validate and return offset and depth as integers if valid. 
    Ensures offset is not greater than depth.
    
    Returns:
        tuple[int | None, int | None]: (offset, depth)
    """
    offset_val = int(offset) if offset and offset.isdigit() else None
    depth_val = int(depth) if depth and depth.isdigit() else None

    if offset_val is not None and depth_val is not None and offset_val > depth_val:
        raise ValueError("Offset cannot be greater than depth.")
    
    return offset_val, depth_val


def _validate_flags(flags: str) -> str:
    """
    Validate TCP flags for Snort rules.
    Allows flag character, modifiers, and separators: F, S, R, P, A, U, C, E, 0, *, +, !, ,
    """
    allowed_chars = set("FSRPAUCE0*+!,")
    if all(c in allowed_chars for c in flags):
        return flags.upper()
    raise ValueError(f"Invalid character in TCP flags: {flags}")


def _validate_pcre(pcre: str) -> str:
    """Validate basic PCRE syntax: must be wrapped in slashes (/pattern/modifiers)."""
    if not (pcre.startswith("/") and "/" in pcre[1:]):
        raise ValueError("Invalid PCRE format. Must start with and have closing '/'.")
    return pcre


def _validate_metadata(data: str) -> str:
    """
    Validate metadata is using key value pairs and comma delimiter.
    Example valid input: "os linux, author admin"
    """
    parts = [item.strip() for item in data.split(",") if item.strip()]

    for part in parts:
        if " " not in part:
            raise ValueError(
                f"Invalid metadata segment '{part}'. Each entry should be a key-value pair like 'key value'."
            )
        key, val = part.split(" ", 1)
        if not key.isidentifier():
            raise ValueError(
                f"Invalid metadata key '{key}'. Keys should be alphanumeric and start with a letter."
            )
        if not val:
            raise ValueError(
                f"Missing value for metadata key '{key}'."
            )
        
    return data


def _validate_msg(value: str) -> str:
    """
    Escape reserved characters in Snort msg fields:
    ; \ " | ' \; → \\ \" \| \;
    
    Returns:
        str: Escaped message string
    """
    reserved = {
        ";": r"\;",
        "\\": r"\\",
        "\"": r"\"",
        "|": r"\|",
        "'": r"\;"
    }

    def escape_char(match):
        """Escape reserved characters if not escaped already"""
        char = match.group(0)
        return reserved[char]
    
    pattern = r'(?<!\\)([;\\\"|\'])'
    escaped = re.sub(pattern, escape_char, value)

    return escaped


def _validate_reference(value: str) -> str:
    """
    Validate that reference is in format scheme,id
    Examples:
        url,http://example.com
        cve,2021-12345
    """
    if "," not in value:
        raise ValueError("Reference must be in format: scheme,id")
    
    scheme, id_ = value.split(",", 1)
    scheme = scheme.strip().lower()
    id_ = id_.strip()

    if not scheme or not id_:
        raise ValueError("Reference must include both scheme and id.")
    
    return f"{scheme},{id_}"


def _argparse_type(func):
    """
    Wrap a validation function for use with argparse type= arguments.
    Converts ValueError to argparse.ArgumentTypeError.
    """
    def wrapper(value):
        try:
            return func(value)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))
    return wrapper


def _get_latest_revision(outfile: str, sid: int) -> int:
    """
    Get the next revision number for a rule based on SID.

    Scans the given file and returns the latest revision + 1 or 1 if the SID is not found.

    Args:
        outfile (str): Path to the rule file.
        sid (int): SID to look for.

    Returns:
        int: The next revision number.
    """
    if not os.path.exists(outfile):
        return 1
    
    rev_pattern = re.compile(rf'sid:{sid};\s*rev:(\d+)')
    max_rev = 0

    with open(outfile, 'r') as f:
        for line in f:
            match = rev_pattern.search(line)
            if match:
                rev = int(match.group(1))
                max_rev = max(max_rev, rev)

    return max_rev + 1 if max_rev else 1


def _resolve(arg_val, config: dict, key: str, fallback=None):
    """
    Resolve a value from multiple sources in order of priority:
    1. Direct CLI argument value (arg_val)
    2. Config file value for the key
    3. Hardcoded fallback default

    Args:
        arg_val (Any): Direct argument (e.g., from argparse).
        config (dict): Loaded config dictionary.
        key (str): Config key to resolve.
        fallback (Any): Default value if key is not found.

    Returns:
        Any: Resolved value
    """
    return arg_val if arg_val is not None else _get_config_value(config, key, fallback)