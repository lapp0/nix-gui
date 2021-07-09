from nixui.options import syntax_tree, nix_eval



def inject_expressions(module_path, option_expr_map):
    option_expr_map = dict(option_expr_map)
    tree = syntax_tree.get_syntax_tree(module_path)

    option_expr_nodes_map = get_key_value_nodes(module_path, tree)

    for attr_loc, expression in option_expr_map.items():
        # update option expressions where they exist
        if attr_loc in option_expr_nodes_map:
            key_node, value_node = option_expr_nodes_map[attr_loc]
            # TODO: fix this hack, we shouldn't be modifying node objects in place (dirty) to get a modified ast
            value_node.name = 'INJECTION'
            value_node.elems = [syntax_tree.Token(name='INJECTION', position=None, quoted=option_expr_map[attr_loc])]
            del option_expr_map[option_expr_map]
        # add new option definitions where they don't exist
        else:
            pass

    return syntax_tree.get_full_node_string(tree)


def get_all_option_values(root_module_path):
    option_expr_map = {}
    for module_path in [root_module_path]:
        tree = syntax_tree.get_syntax_tree(module_path)
        for attr_loc, (key_node, value_node) in get_key_value_nodes(module_path, tree).items():
            value_expr = syntax_tree.get_full_node_string(value_node)
            option_expr_map[attr_loc] = value_expr
    return option_expr_map


def get_option_definitions_attr_set(module_path, syntax_tree):
    """
    Get the attribute set containing option definitions which is returned by the module
    """
    tree = syntax_tree.get_syntax_tree(module_path)
    mapping = {}
    for attr_loc, attr_data in nix_eval.get_modules_defined_attrs(module_path).items():
        character_index = get_column_line_index_map(module_path)(
            attr_data['position']['line'] - 1,
            attr_data['position']['column'] - 1
        )  # 'line' and 'column' are 1-indexed
        definition_node = syntax_tree.get_node_at_position(
            tree,
            character_index,
            'NODE_KEY_VALUE'
        )
        key_node, value_node = [e for e in definition_node.elems if isinstance(e, syntax_tree.Node)]
        mapping[attr_loc] = (key_node, value_node)
    return mapping


def get_key_value_nodes(module_path, tree):
    mapping = {}
    for attr_loc, attr_data in nix_eval.get_modules_defined_attrs(module_path).items():
        character_index = get_column_line_index_map(module_path)(
            attr_data['position']['line'] - 1,
            attr_data['position']['column'] - 1
        )  # 'line' and 'column' are 1-indexed
        definition_node = syntax_tree.get_node_at_position(
            tree,
            character_index,
            'NODE_KEY_VALUE'
        )
        key_node, value_node = [e for e in definition_node.elems if isinstance(e, syntax_tree.Node)]
        mapping[attr_loc] = (key_node, value_node)
    return mapping


def get_column_line_index_map(path):
    line_index_map = {}
    index = 0
    with open(path) as f:
        for i, line in enumerate(f.readlines()):
            line_index_map[i] = index
            index += len(line.encode("utf8"))

    mapper = lambda line, col: line_index_map[line] + col
    return mapper


def get_imported_modules(module_path):
    return nix_eval.eval_attribute(module_path, "imports")
