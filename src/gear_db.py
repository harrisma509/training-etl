def format_gear_display_name(brand, model_year, gear_name, fallback):
    parts = []

    if model_year:
        parts.append(str(model_year))

    if brand:
        parts.append(brand)

    if gear_name:
        parts.append(gear_name)

    return " ".join(parts) if parts else fallback


def fetch_gear_display_map(cfg):
    import psycopg

    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    gear_id,
                    brand,
                    model_year,
                    gear_name
                FROM gear
            """)
            rows = cur.fetchall()

    gear_display_map = {}

    for gear_id, brand, model_year, gear_name in rows:
        gear_display_map[gear_id] = format_gear_display_name(
            brand=brand,
            model_year=model_year,
            gear_name=gear_name,
            fallback=gear_id,
        )

    return gear_display_map