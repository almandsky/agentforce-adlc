"""Generate Apex @InvocableMethod stubs for .agent file action targets."""

from __future__ import annotations

# Mapping from .agent types to Apex types
_TYPE_MAP = {
    "string": "String",
    "number": "Decimal",
    "boolean": "Boolean",
    "date": "Date",
    "datetime": "Datetime",
    "id": "Id",
    "object": "Map<String, Object>",
}

# Mapping from complex_data_type_name to Apex types (for action I/O)
_COMPLEX_TYPE_MAP = {
    "lightning__integerType": "Integer",
    "lightning__doubleType": "Double",
    "lightning__currencyType": "Decimal",
    "lightning__dateTimeStringType": "Datetime",
    "lightning__recordInfoType": "SObject",
    "lightning__objectType": "Map<String, Object>",
    "lightning__listType": "List<Object>",
    "lightning__textType": "String",
}

API_VERSION = "66.0"


def generate_apex_class(
    class_name: str,
    inputs: list[dict] | None = None,
    outputs: list[dict] | None = None,
) -> str:
    """Generate an Apex class with @InvocableMethod stub.

    Produces a class with:
    - Inner Request class with @InvocableVariable fields for each input
    - Inner Response class with @InvocableVariable fields for each output
    - @InvocableMethod static method returning placeholder response

    Args:
        class_name: The Apex class name.
        inputs: Action input definitions (list of dicts with 'name', 'type' keys).
        outputs: Action output definitions (list of dicts with 'name', 'type' keys).

    Returns:
        Apex class source code string.
    """
    inputs = inputs or []
    outputs = outputs or []

    lines = [
        f'public with sharing class {class_name} {{',
        '',
    ]

    # Request inner class
    lines.append('    public class Request {')
    for inp in inputs:
        apex_type = _COMPLEX_TYPE_MAP.get(inp.get("complex_data_type_name", ""), _TYPE_MAP.get(inp.get("type", "string"), "String"))
        desc = inp.get("description", "")
        is_req = inp.get("required", True)
        if desc:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(desc)}\' required={_apex_bool(is_req)})')
        else:
            lines.append(f'        @InvocableVariable(required={_apex_bool(is_req)})')
        lines.append(f'        public {apex_type} {inp["name"]};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # Response inner class
    lines.append('    public class Response {')
    for out in outputs:
        apex_type = _COMPLEX_TYPE_MAP.get(out.get("complex_data_type_name", ""), _TYPE_MAP.get(out.get("type", "string"), "String"))
        desc = out.get("description", "")
        if desc:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(desc)}\')')
        else:
            lines.append(f'        @InvocableVariable')
        lines.append(f'        public {apex_type} {out["name"]};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # @InvocableMethod
    method_label = _class_to_label(class_name)
    lines.extend([
        f'    @InvocableMethod(label=\'{method_label}\' description=\'TODO: Add description\')',
        '    public static List<Response> invoke(List<Request> requests) {',
        '        List<Response> responses = new List<Response>();',
        '        for (Request req : requests) {',
        '            Response res = new Response();',
        '            // TODO: Implement business logic',
    ])

    for out in outputs:
        default = _default_for_type(out.get("type", "string"))
        lines.append(f'            res.{out["name"]} = {default};')

    lines.extend([
        '            responses.add(res);',
        '        }',
        '        return responses;',
        '    }',
        '}',
    ])

    return "\n".join(lines) + "\n"


def generate_apex_meta_xml(api_version: str = API_VERSION) -> str:
    """Generate the .cls-meta.xml companion file."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f'    <apiVersion>{api_version}</apiVersion>\n'
        '    <status>Active</status>\n'
        '</ApexClass>\n'
    )


def _escape_apex(text: str) -> str:
    """Escape special characters for Apex strings."""
    return (text
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t"))


def _apex_bool(value: bool) -> str:
    """Format boolean for Apex (lowercase)."""
    return "true" if value else "false"


def _class_to_label(class_name: str) -> str:
    """Convert PascalCase class name to a human-readable label."""
    result = []
    for i, ch in enumerate(class_name):
        if ch.isupper() and i > 0 and not class_name[i - 1].isupper():
            result.append(" ")
        result.append(ch)
    return "".join(result)


def _default_for_type(type_name: str) -> str:
    """Return a placeholder Apex default value literal."""
    defaults = {
        "string": "'TODO'",
        "number": "0",
        "boolean": "false",
        "date": "Date.today()",
        "datetime": "Datetime.now()",
        "id": "null",
    }
    return defaults.get(type_name, "null")
