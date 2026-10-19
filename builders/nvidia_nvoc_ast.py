"""Bind a lowered NVOC member load to Clang's actual typed source expression.

A byte GEP alone proves no C type. This narrow fallback requires the original
translation unit's AST, the exact generated inline wrapper/FieldDecl relation,
and the optimized load/call's compiler locations through to the measured root.
Unsupported AST or debug forms remain unknown. No stack bound is assigned.
"""
from __future__ import annotations

from pathlib import Path
import re


def _one(values, message):
    if len(values) != 1:
        raise ValueError(message)
    return values[0]


def _unwrap(node, cast):
    if node.get('kind') != 'ImplicitCastExpr' or node.get('castKind') != cast:
        raise ValueError('NVOC AST requires the exact implicit conversion: ' + cast)
    return _one(node.get('inner', []), 'Ambiguous NVOC AST conversion.')


def _position(location, text):
    # Macro spelling/expansion needs a separate proof. This generated wrapper
    # and its field declaration contain neither; do not select one location.
    if 'spellingLoc' in location or 'expansionLoc' in location:
        raise ValueError('Macro-expanded NVOC AST location requires separate review.')
    offset, size = location.get('offset'), location.get('tokLen')
    if not isinstance(offset, int) or not isinstance(size, int) or offset < 0 or size < 1:
        raise ValueError('NVOC AST lacks a bounded source token location.')
    if offset + size > len(text):
        raise ValueError('NVOC AST source token is out of bounds.')
    line = text.count('\n', 0, offset) + 1
    column = offset - text.rfind('\n', 0, offset)
    if location.get('line', line) != line or location.get('col', column) != column:
        raise ValueError('NVOC AST line/column differs from the actual source bytes.')
    return {'line': line, 'column': column, 'token': text[offset:offset + size]}


def member_binding(document, *, owner, field, wrapper, header, dispatch_line):
    """Require actual FieldDecl identity, a typed parameter, and one return call.

    The whole AST comes from one compiler invocation so declaration IDs are
    meaningful; IDs from separate filtered dumps must never be joined.
    """
    if document.get('kind') != 'TranslationUnitDecl':
        raise ValueError('NVOC requires one complete actual translation-unit AST.')
    top = document.get('inner', [])
    record = _one([node for node in top if node.get('kind') == 'RecordDecl'
                   and node.get('name') == owner and node.get('completeDefinition')],
                  'NVOC AST requires one complete unambiguous owner record.')
    member = _one([node for node in record.get('inner', [])
                   if node.get('kind') == 'FieldDecl' and node.get('name') == field],
                  'NVOC AST requires one exact owner FieldDecl.')
    function = _one([node for node in top if node.get('kind') == 'FunctionDecl'
                     and node.get('name') == wrapper
                     and any(child.get('kind') == 'CompoundStmt' for child in node.get('inner', []))],
                    'NVOC AST requires one actual generated wrapper definition.')
    if function.get('storageClass') != 'static' or function.get('inline') is not True:
        raise ValueError('NVOC AST wrapper must be the actual static inline dispatch.')
    body = _one([node for node in function.get('inner', []) if node.get('kind') == 'CompoundStmt'],
                'NVOC AST wrapper body is ambiguous.')
    returned = _one(body.get('inner', []), 'NVOC AST wrapper must contain only one return.')
    if returned.get('kind') != 'ReturnStmt':
        raise ValueError('NVOC AST wrapper is not one returned dispatch.')
    call = _one(returned.get('inner', []), 'NVOC AST return is ambiguous.')
    if call.get('kind') != 'CallExpr' or len(call.get('inner', [])) < 2:
        raise ValueError('NVOC AST return is not one direct member call.')
    callee = _unwrap(call['inner'][0], 'LValueToRValue')
    if (callee.get('kind') != 'MemberExpr' or callee.get('name') != field
            or callee.get('isArrow') is not True
            or callee.get('referencedMemberDecl') != member.get('id')
            or not member.get('id') or callee.get('type') != member.get('type')):
        raise ValueError('NVOC AST callee does not reference the exact typed owner FieldDecl.')
    receiver = _unwrap(_one(callee.get('inner', []), 'Ambiguous NVOC AST receiver.'), 'LValueToRValue')
    argument = _unwrap(call['inner'][1], 'LValueToRValue')
    params = [node for node in function.get('inner', []) if node.get('kind') == 'ParmVarDecl']
    parameter = _one([node for node in params if node.get('id') ==
                      receiver.get('referencedDecl', {}).get('id')],
                     'NVOC AST receiver must be one actual wrapper parameter.')
    if (receiver.get('kind') != 'DeclRefExpr' or argument.get('kind') != 'DeclRefExpr'
            or argument.get('referencedDecl', {}).get('id') != parameter.get('id')
            or parameter.get('type', {}).get('qualType') != 'struct ' + owner + ' *'
            or receiver.get('referencedDecl', {}).get('kind') != 'ParmVarDecl'):
        raise ValueError('NVOC AST receiver/call argument is not the same typed owner parameter.')
    # Clang offsets count source bytes. Refuse an encoding whose character
    # offsets would differ rather than silently comparing the wrong token.
    text = header.read_bytes().decode('ascii')
    declaration = _position(member.get('loc', {}), text)
    function_position = _position(function.get('loc', {}), text)
    member_position = _position(callee.get('range', {}).get('end', {}), text)
    callee_position = _position(callee.get('range', {}).get('begin', {}), text)
    call_position = _position(call.get('range', {}).get('begin', {}), text)
    if (declaration['token'] != field or member_position['token'] != field
            or function_position['token'] != wrapper
            or member_position['line'] != dispatch_line or call_position['line'] != dispatch_line):
        raise ValueError('NVOC AST tokens differ from the catalogued generated source.')
    return {'owner': owner, 'field': field, 'wrapper': wrapper,
            'field_declaration': declaration, 'wrapper_declaration': function_position,
            'member_expression': member_position, 'callee_expression': callee_position,
            'call_expression': call_position,
            'field_type': member['type'], 'receiver_type': parameter['type'],
            'same_translation_unit_field_identity': True}


def _string(text, field):
    match = re.search(r'\b' + field + r': "((?:[^"\\]|\\[0-9A-Fa-f]{2})*)"', text)
    if not match:
        raise ValueError('Missing/unsupported LLVM debug string: ' + field)
    return re.sub(r'\\([0-9A-Fa-f]{2})', lambda value: chr(int(value[1], 16)), match[1])


def _ref(text, field):
    match = re.search(r'\b' + field + r': !(\d+)\b', text)
    if not match:
        raise ValueError('Missing LLVM debug reference: ' + field)
    return match[1]


def debug_member_binding(text, *, function, load, call, header, source, cwd, binding):
    """Require both optimized instructions to name the exact AST source tokens."""
    metadata = dict(re.findall(r'^!(\d+) = (.+)$', text, re.M))

    def item(number, kind):
        value = metadata.get(number, '')
        if not re.match(r'(?:distinct )?!' + kind + r'\(', value):
            raise ValueError('Unsupported/missing LLVM debug node: ' + kind)
        return value

    def file_of(subprogram):
        value = item(_ref(subprogram, 'file'), 'DIFile')
        filename = Path(_string(value, 'filename'))
        directory = Path(_string(value, 'directory'))
        path = filename if filename.is_absolute() else directory / filename
        return (path if path.is_absolute() else cwd / path).resolve()

    def subprogram_of(location):
        number = _ref(location, 'scope')
        seen = set()
        while number not in seen:
            seen.add(number)
            value = metadata.get(number, '')
            if re.match(r'(?:distinct )?!DISubprogram\(', value):
                return value
            if not re.match(r'(?:distinct )?!DILexicalBlock(?:File)?\(', value):
                break
            number = _ref(value, 'scope')
        raise ValueError('LLVM debug scope is not one acyclic function scope.')

    def location(instruction, expected):
        refs = re.findall(r'(?:,\s*)!dbg !(\d+)\b', instruction)
        number = _one(refs, 'Lowered NVOC instruction requires one actual debug location.')
        value = item(number, 'DILocation')
        line = re.search(r'\bline: (\d+)\b', value)
        column = re.search(r'\bcolumn: (\d+)\b', value)
        scope = subprogram_of(value)
        if (not line or not column or not any(int(line[1]) == point['line']
                and int(column[1]) == point['column'] for point in expected)
                or _string(scope, 'name') != binding['wrapper'] or file_of(scope) != header.resolve()):
            raise ValueError('Lowered NVOC instruction does not bind the actual AST member/call token.')
        origin = number
        seen = set()
        chain = []
        while number not in seen:
            seen.add(number)
            value = item(number, 'DILocation')
            scope = subprogram_of(value)
            chain.append({'function': _string(scope, 'name'), 'source': str(file_of(scope))})
            parent = re.search(r'\binlinedAt: !(\d+)\b', value)
            if not parent:
                if chain[-1] != {'function': function, 'source': str(source.resolve())}:
                    raise ValueError('Lowered NVOC inline provenance does not reach the measured root.')
                return {'location': origin, 'inline_chain': chain}
            number = parent[1]
        raise ValueError('Cyclic LLVM inline provenance.')

    # Apple Clang 17 locates the load at the beginning of the full callee
    # expression; Clang 18 uses its final field token. Both positions come
    # from this actual AST. Other columns on the same line are not accepted.
    loaded = location(load, [binding['member_expression'], binding['callee_expression']])
    called = location(call, [binding['call_expression']])
    if loaded['inline_chain'] != called['inline_chain']:
        raise ValueError('NVOC load and call have different source inline provenance.')
    # Same functions alone do not identify the same inline call instance.
    load_loc = item(loaded['location'], 'DILocation')
    call_loc = item(called['location'], 'DILocation')
    if _ref(load_loc, 'inlinedAt') != _ref(call_loc, 'inlinedAt'):
        raise ValueError('NVOC load and call belong to different inline call instances.')
    return {'ast': binding, 'optimized_load': loaded, 'optimized_call': called,
            'binding': 'actual-field-declaration-and-compiler-inline-source-tokens'}
