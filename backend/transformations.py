"""
Transformation engine — builds dynamic SQL from user-configured transformations.
Each source table is loaded through a SELECT that applies filters, null-handling,
and value transformations before inserting into the warehouse.
"""

# Columns available per source table (for validation + frontend)
SOURCE_COLUMNS = {
    "clients":      ["id_client", "nom", "prenom", "date_naissance", "ville", "solde"],
    "comptes":      ["id_compte", "id_client", "type_compte", "date_ouverture", "solde", "statut"],
    "agences":      ["id_agence", "nom_agence", "ville", "region", "telephone"],
    "transactions": ["id_transaction", "id_compte", "date_transaction", "montant", "type_operation", "description"],
}

# Allowed filter operators mapped to SQL
FILTER_OPERATORS = {
    "=":        "=",
    "!=":       "!=",
    ">":        ">",
    "<":        "<",
    ">=":       ">=",
    "<=":       "<=",
    "contains": "ILIKE",
}

def _quote_value(value, operator):
    """Safely format a value for SQL. Numbers stay unquoted, strings get quoted."""
    if operator == "contains":
        return f"'%{value}%'"
    # Try to treat as number
    try:
        float(value)
        return str(value)
    except (ValueError, TypeError):
        # It's a string — escape single quotes and wrap
        safe = str(value).replace("'", "''")
        return f"'{safe}'"

def build_column_expression(col, transforms):
    """
    Build the SELECT expression for a single column, applying any value
    transformations that target it.
    """
    expr = f"s.{col}"
    for t in transforms:
        if t.get("type") != "transform_value":
            continue
        cfg = t.get("config", {})
        if cfg.get("column") != col:
            continue
        op = cfg.get("operation")
        if op == "uppercase":
            expr = f"UPPER({expr})"
        elif op == "lowercase":
            expr = f"LOWER({expr})"
        elif op == "trim":
            expr = f"TRIM({expr})"
        elif op == "round":
            expr = f"ROUND({expr}::numeric, 2)"
    return expr

def build_select(source_table, transforms):
    """
    Build a full SELECT statement from staging.<source_table>, applying:
      - value transformations (in the SELECT columns)
      - filters (WHERE)
      - null cleaning (WHERE ... IS NOT NULL  or COALESCE)
    Returns the SQL string (a SELECT) and a human-readable summary list.
    """
    cols = SOURCE_COLUMNS.get(source_table, [])
    if not cols:
        return None, ["Unknown source table"]

    summary = []

    # Build SELECT expressions (with value transforms + null replacements)
    select_exprs = []
    for col in cols:
        expr = build_column_expression(col, transforms)

        # Null replacement (clean_nulls with replace action)
        for t in transforms:
            if t.get("type") != "clean_nulls":
                continue
            cfg = t.get("config", {})
            if cfg.get("column") == col and cfg.get("action") == "replace":
                default = cfg.get("default_value", "")
                quoted = _quote_value(default, "=")
                expr = f"COALESCE({expr}, {quoted})"

        select_exprs.append(f"{expr} AS {col}")

    sql = f"SELECT {', '.join(select_exprs)} FROM staging.{source_table} s"

    # Build WHERE clauses
    where_clauses = []

    for t in transforms:
        ttype = t.get("type")
        cfg = t.get("config", {})

        if ttype == "filter":
            col = cfg.get("column")
            op = cfg.get("operator")
            val = cfg.get("value")
            if col and op in FILTER_OPERATORS and val is not None and val != "":
                sql_op = FILTER_OPERATORS[op]
                quoted = _quote_value(val, op)
                where_clauses.append(f"s.{col} {sql_op} {quoted}")
                summary.append(f"Filter: {col} {op} {val}")

        elif ttype == "clean_nulls":
            col = cfg.get("column")
            action = cfg.get("action")
            if col and action == "drop":
                where_clauses.append(f"s.{col} IS NOT NULL AND s.{col}::text != ''")
                summary.append(f"Drop rows where {col} is empty")
            elif col and action == "replace":
                summary.append(f"Replace empty {col} with '{cfg.get('default_value','')}'")

        elif ttype == "transform_value":
            col = cfg.get("column")
            op = cfg.get("operation")
            if col and op:
                summary.append(f"Transform: {op} {col}")

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    return sql, summary