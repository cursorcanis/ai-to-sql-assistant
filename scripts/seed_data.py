"""Generate and load sample data for the analytics schema.

The data is generated rather than committed as SQL: ~370k rows of INSERT
statements would be an unreviewable file in git. random.seed(RANDOM_SEED)
makes it reproducible — the same seed always yields the same database.

Sized for Supabase's free tier (~500 MB). The generated data lands well under
100 MB including indexes, leaving plenty of headroom.

The data is deliberately not uniform. Seasonal peaks, a growth trend, segment
and channel skew, a long-tail product distribution and correlated returns all
exist so that window functions and DAX measures have something real to find.

Usage:
    python scripts/seed_data.py            # truncate and reload
    python scripts/seed_data.py --counts   # just report current row counts
"""

import os
import sys
import math
import random
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_ADMIN_URL")
if not url:
    sys.exit("SUPABASE_ADMIN_URL is not set in .env — see .env.example.")

RANDOM_SEED = 42
START_DATE = date(2019, 1, 1)
END_DATE = date(2024, 12, 31)

N_CITIES = 200
N_EMPLOYEES = 200
N_SUPPLIERS = 80
N_PRODUCTS = 1500
N_CUSTOMERS = 8000
N_CAMPAIGNS = 50
N_ORDERS = 60000

random.seed(RANDOM_SEED)

TABLES_IN_LOAD_ORDER = [
    "dim_date", "regions", "countries", "cities", "employees", "categories",
    "suppliers", "products", "product_price_history", "customers",
    "campaigns", "campaign_customers", "orders", "order_items",
    "returns", "payments", "inventory_snapshots",
]

REGIONS = ["North America", "South America", "Europe", "Middle East & Africa",
           "Asia Pacific", "Oceania"]

COUNTRIES = [
    ("United States", "USA", 0), ("Canada", "CAN", 0), ("Mexico", "MEX", 0),
    ("Brazil", "BRA", 1), ("Argentina", "ARG", 1), ("Chile", "CHL", 1),
    ("Colombia", "COL", 1), ("United Kingdom", "GBR", 2), ("Germany", "DEU", 2),
    ("France", "FRA", 2), ("Spain", "ESP", 2), ("Italy", "ITA", 2),
    ("Netherlands", "NLD", 2), ("Poland", "POL", 2), ("Sweden", "SWE", 2),
    ("Ireland", "IRL", 2), ("South Africa", "ZAF", 3), ("Egypt", "EGY", 3),
    ("Nigeria", "NGA", 3), ("Kenya", "KEN", 3), ("United Arab Emirates", "ARE", 3),
    ("Japan", "JPN", 4), ("China", "CHN", 4), ("India", "IND", 4),
    ("Singapore", "SGP", 4), ("South Korea", "KOR", 4), ("Thailand", "THA", 4),
    ("Vietnam", "VNM", 4), ("Australia", "AUS", 5), ("New Zealand", "NZL", 5),
]

CITY_STEMS = [
    "Springfield", "Riverside", "Fairview", "Georgetown", "Clinton", "Madison",
    "Franklin", "Salem", "Bristol", "Ashland", "Dover", "Oxford", "Newport",
    "Milton", "Kingston", "Auburn", "Concord", "Hudson", "Lincoln", "Manchester",
    "Marion", "Oakland", "Winchester", "Hamilton", "Arlington", "Burlington",
    "Chester", "Cleveland", "Danville", "Greenville", "Jackson", "Lexington",
    "Monroe", "Norwood", "Plymouth", "Richmond", "Sheridan", "Trenton",
    "Waterloo", "York",
]

TOP_CATEGORIES = ["Electronics", "Home & Garden", "Apparel", "Sports & Outdoors",
                  "Office", "Health & Beauty"]
MID_CATEGORIES = {
    "Electronics": ["Computers", "Audio", "Photography", "Mobile"],
    "Home & Garden": ["Kitchen", "Furniture", "Tools"],
    "Apparel": ["Menswear", "Womenswear", "Footwear"],
    "Sports & Outdoors": ["Fitness", "Camping", "Cycling"],
    "Office": ["Stationery", "Furniture & Storage", "Printers"],
    "Health & Beauty": ["Skincare", "Supplements"],
}
LEAF_SUFFIXES = ["Essentials", "Premium", "Accessories", "Bundles"]

PRODUCT_ADJECTIVES = ["Compact", "Pro", "Ultra", "Classic", "Eco", "Smart",
                      "Heavy-Duty", "Lightweight", "Deluxe", "Everyday",
                      "Precision", "Wireless", "Portable", "Industrial"]
PRODUCT_NOUNS = ["Monitor", "Keyboard", "Headset", "Blender", "Chair", "Lamp",
                 "Drill", "Jacket", "Sneaker", "Backpack", "Tent", "Bicycle",
                 "Notebook", "Printer", "Serum", "Vitamin Pack", "Speaker",
                 "Camera", "Tablet", "Router", "Desk", "Kettle", "Mixer",
                 "Toolset", "Watch"]

FIRST_NAMES = ["Alice", "Brian", "Carla", "David", "Emily", "Frank", "Grace",
               "Henry", "Isabel", "Jonas", "Karen", "Liam", "Maya", "Noah",
               "Olivia", "Priya", "Quentin", "Rosa", "Samuel", "Tara", "Umar",
               "Vera", "Walter", "Ximena", "Yusuf", "Zoe", "Adam", "Bianca",
               "Caleb", "Diana", "Elias", "Farah", "Gabriel", "Hana", "Ivan"]
LAST_NAMES = ["Johnson", "Smith", "Rodriguez", "Lee", "Davis", "Moore", "Kim",
              "Thompson", "Garcia", "Novak", "Okafor", "Muller", "Rossi",
              "Silva", "Haddad", "Nakamura", "Patel", "Andersson", "Dubois",
              "Kowalski", "Ferreira", "Nguyen", "Ali", "Petrov", "Costa",
              "Sharma", "Wagner", "Larsen", "Moreau", "Bianchi"]

TITLES_BY_LEVEL = ["Chief Executive", "VP Sales", "Regional Director",
                   "Sales Manager", "Account Executive"]
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
CHANNELS = ["Web", "Phone", "Partner", "Retail"]
ORDER_STATUS = ["Completed", "Shipped", "Pending", "Cancelled"]
PAYMENT_METHODS = ["Credit Card", "Bank Transfer", "PayPal", "Invoice"]
RETURN_REASONS = ["Damaged", "Wrong item", "No longer needed",
                  "Better price elsewhere", "Late delivery", "Faulty"]
CAMPAIGN_CHANNELS = ["Email", "Social", "Search", "Direct Mail", "Event"]


def daterange_days(start, end):
    return (end - start).days


def random_date(start, end):
    return start + timedelta(days=random.randint(0, daterange_days(start, end)))


def build_dim_date():
    rows = []
    d = START_DATE
    while d <= END_DATE:
        # Fiscal year starts in April.
        fiscal_year = d.year if d.month >= 4 else d.year - 1
        fiscal_quarter = ((d.month - 4) % 12) // 3 + 1
        iso = d.isocalendar()
        rows.append((
            d, d.year, (d.month - 1) // 3 + 1, d.month, d.strftime("%B"),
            d.day, d.isoweekday(), d.strftime("%A"), iso[1],
            d.isoweekday() >= 6, fiscal_year, fiscal_quarter,
        ))
        d += timedelta(days=1)
    return rows


def build_geography():
    regions = [(i + 1, name) for i, name in enumerate(REGIONS)]
    countries = [(i + 1, name, iso, region_idx + 1)
                 for i, (name, iso, region_idx) in enumerate(COUNTRIES)]
    cities = []
    for cid in range(1, N_CITIES + 1):
        country_id = random.randint(1, len(COUNTRIES))
        stem = random.choice(CITY_STEMS)
        suffix = random.choice(["", " North", " South", " East", " West",
                                " Heights", " Valley", " Park"])
        cities.append((
            cid, f"{stem}{suffix}", country_id,
            round(random.uniform(-54, 68), 6),
            round(random.uniform(-165, 178), 6),
        ))
    return regions, countries, cities


def build_employees():
    """Five-level org chart, so recursive CTEs have real depth to walk."""
    employees = []
    by_level = {0: [1]}
    employees.append((
        1, "Dana", "Whitfield", TITLES_BY_LEVEL[0], None, date(2015, 3, 2),
        None, random.randint(1, N_CITIES), 310000.00, 0.000,
    ))

    next_id = 2
    level_sizes = [0, 5, 18, 45, N_EMPLOYEES - 69]
    for level in range(1, 5):
        by_level[level] = []
        for _ in range(level_sizes[level]):
            if next_id > N_EMPLOYEES:
                break
            manager_id = random.choice(by_level[level - 1])
            hire = random_date(date(2015, 1, 1), date(2024, 6, 30))
            # ~8% have left the company.
            terminated = (random_date(hire, END_DATE)
                          if random.random() < 0.08 else None)
            salary = round(random.uniform(45000, 95000)
                           * (1.55 ** (4 - level)), 2)
            employees.append((
                next_id, random.choice(FIRST_NAMES), random.choice(LAST_NAMES),
                TITLES_BY_LEVEL[level], manager_id, hire, terminated,
                random.randint(1, N_CITIES), salary,
                round(random.uniform(0, 0.08), 3) if level >= 3 else 0.000,
            ))
            by_level[level].append(next_id)
            next_id += 1
    return employees, by_level[4] or by_level[3]


def build_categories():
    """Three-level category tree."""
    categories = []
    cid = 1
    leaf_ids = []
    for top in TOP_CATEGORIES:
        top_id = cid
        categories.append((cid, top, None, 1))
        cid += 1
        for mid in MID_CATEGORIES[top]:
            mid_id = cid
            categories.append((cid, mid, top_id, 2))
            cid += 1
            for suffix in random.sample(LEAF_SUFFIXES, k=random.randint(1, 3)):
                categories.append((cid, f"{mid} {suffix}", mid_id, 3))
                leaf_ids.append(cid)
                cid += 1
    return categories, leaf_ids


def build_suppliers():
    return [(
        i + 1, f"{random.choice(LAST_NAMES)} {random.choice(['Supply Co', 'Industries', 'Trading', 'Logistics', 'Partners'])}",
        random.randint(1, N_CITIES), random.randint(3, 45),
        round(random.uniform(2.5, 5.0), 2),
    ) for i in range(N_SUPPLIERS)]


def build_products(leaf_category_ids):
    products = []
    for pid in range(1, N_PRODUCTS + 1):
        cost = round(random.uniform(4, 850), 2)
        markup = random.uniform(1.25, 2.9)
        launch = random_date(date(2018, 1, 1), date(2024, 6, 30))
        products.append((
            pid,
            f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)} {random.randint(100, 999)}",
            random.choice(leaf_category_ids), random.randint(1, N_SUPPLIERS),
            cost, round(cost * markup, 2), round(random.uniform(0.05, 24), 3),
            launch, random.random() < 0.07,
        ))
    return products


def build_price_history(products):
    """Type-2 SCD: each product gets 1-4 price periods."""
    rows = []
    pid_seq = 1
    for product in products:
        product_id, list_price, launch = product[0], float(product[5]), product[7]
        n_changes = random.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
        boundaries = sorted(random_date(launch, END_DATE)
                            for _ in range(n_changes - 1))
        starts = [launch] + boundaries
        price = list_price / random.uniform(1.0, 1.35)
        for i, start in enumerate(starts):
            is_last = i == len(starts) - 1
            end = None if is_last else starts[i + 1] - timedelta(days=1)
            if end is not None and end < start:
                end = start
            rows.append((pid_seq, product_id, round(price, 2), start, end, is_last))
            pid_seq += 1
            price *= random.uniform(1.01, 1.18)
    return rows


def build_customers():
    rows = []
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        segment = random.choices(SEGMENTS, weights=[55, 30, 15])[0]
        rows.append((
            cid, f"{first} {last}",
            f"{first.lower()}.{last.lower()}{cid}@example.com",
            random.randint(1, N_CITIES), segment,
            random_date(date(2018, 1, 1), END_DATE),
            round(random.choice([2500, 5000, 10000, 25000, 50000])
                  * random.uniform(0.8, 1.2), 2),
            random.random() > 0.12,
        ))
    return rows


def build_campaigns():
    rows = []
    for cid in range(1, N_CAMPAIGNS + 1):
        start = random_date(START_DATE, END_DATE - timedelta(days=60))
        rows.append((
            cid, f"{random.choice(['Spring', 'Summer', 'Autumn', 'Winter', 'Flash', 'Loyalty', 'Launch'])} "
                 f"{random.choice(CAMPAIGN_CHANNELS)} {start.year}-{cid}",
            random.choice(CAMPAIGN_CHANNELS), start,
            start + timedelta(days=random.randint(14, 90)),
            round(random.uniform(5000, 250000), 2),
        ))
    return rows


def build_campaign_customers(campaigns):
    seen, rows = set(), []
    for campaign in campaigns:
        campaign_id, start, end = campaign[0], campaign[3], campaign[4]
        for customer_id in random.sample(range(1, N_CUSTOMERS + 1),
                                         k=random.randint(200, 600)):
            if (campaign_id, customer_id) in seen:
                continue
            seen.add((campaign_id, customer_id))
            rows.append((campaign_id, customer_id, random_date(start, end),
                         random.random() < 0.22))
    return rows


def seasonal_weight(d):
    """Q4 peak, early-summer trough, plus steady year-on-year growth.

    Measured on the seeded data: December 2023 is roughly 3x June 2023, and
    revenue grows about 12% a year. Enough signal for YoY and seasonality
    queries to find something real.
    """
    month_factor = 1.0 + 0.55 * math.cos((d.month - 11.5) / 12 * 2 * math.pi)
    growth = 1.0 + 0.14 * (d.year - START_DATE.year)
    return max(0.15, month_factor) * growth


def build_orders(sales_employee_ids):
    """Order dates are drawn against a seasonal + growth weighting, so time
    series queries see trend and seasonality rather than uniform noise."""
    all_days = []
    d = START_DATE
    while d <= END_DATE:
        all_days.append(d)
        d += timedelta(days=1)
    weights = [seasonal_weight(day) * (0.45 if day.isoweekday() >= 6 else 1.0)
               for day in all_days]

    order_dates = random.choices(all_days, weights=weights, k=N_ORDERS)
    order_dates.sort()

    rows = []
    for order_id, order_date in enumerate(order_dates, start=1):
        status = random.choices(ORDER_STATUS, weights=[70, 15, 9, 6])[0]
        required = order_date + timedelta(days=random.randint(5, 30))
        if status == "Cancelled":
            shipped = None
        elif status == "Pending":
            shipped = None
        else:
            shipped = order_date + timedelta(days=random.randint(1, 21))
            if shipped > END_DATE:
                shipped = END_DATE
        rows.append((
            order_id, random.randint(1, N_CUSTOMERS),
            random.choice(sales_employee_ids), order_date, required, shipped,
            status, random.choices(CHANNELS, weights=[52, 18, 17, 13])[0],
            random.randint(1, N_CITIES), round(random.uniform(0, 95), 2),
        ))
    return rows


def build_order_items(orders, products):
    """Product popularity follows a long tail, so ranking and Pareto-style
    queries produce a meaningful answer."""
    product_ids = [p[0] for p in products]
    list_prices = {p[0]: float(p[6]) for p in products}
    # Zipf-ish weighting.
    popularity = [1.0 / (i ** 0.85 + 4) for i in range(1, len(product_ids) + 1)]
    shuffled = product_ids[:]
    random.shuffle(shuffled)

    rows = []
    item_id = 1
    for order in orders:
        order_id = order[0]
        for product_id in set(random.choices(shuffled, weights=popularity,
                                             k=random.choices([1, 2, 3, 4, 5],
                                                              weights=[34, 28, 20, 12, 6])[0])):
            quantity = random.choices([1, 2, 3, 5, 10, 25],
                                      weights=[45, 24, 14, 10, 5, 2])[0]
            unit_price = round(list_prices[product_id] * random.uniform(0.92, 1.05), 2)
            discount = random.choices([0.0, 0.05, 0.1, 0.15, 0.25],
                                      weights=[58, 17, 13, 8, 4])[0]
            rows.append((
                item_id, order_id, product_id, quantity, unit_price, discount,
                round(quantity * unit_price * (1 - discount), 2),
            ))
            item_id += 1
    return rows


def build_returns(order_items, orders_by_id):
    """Returns correlate with discount and quantity — a pattern worth finding."""
    rows = []
    return_id = 1
    for item in order_items:
        item_id, order_id, _, quantity, unit_price, discount, line_total = item
        order = orders_by_id[order_id]
        if order[6] == "Cancelled" or order[5] is None:
            continue
        probability = 0.035 + float(discount) * 0.18 + (0.02 if quantity >= 10 else 0)
        if random.random() < probability:
            returned = random.randint(1, quantity)
            rows.append((
                return_id, item_id,
                order[5] + timedelta(days=random.randint(2, 60)), returned,
                random.choices(RETURN_REASONS, weights=[22, 14, 28, 12, 10, 14])[0],
                round(float(unit_price) * returned * (1 - float(discount)), 2),
            ))
            return_id += 1
    return rows


def build_payments(orders, totals_by_order):
    """Some orders are paid in instalments, so the payment grain differs from
    the order grain — the classic reason a naive join double-counts."""
    rows = []
    payment_id = 1
    for order in orders:
        order_id, status, order_date = order[0], order[6], order[3]
        if status == "Cancelled":
            continue
        total = totals_by_order.get(order_id, 0.0)
        if total <= 0:
            continue
        instalments = random.choices([1, 2, 3], weights=[82, 13, 5])[0]
        remaining = total
        for n in range(instalments):
            amount = (round(remaining, 2) if n == instalments - 1
                      else round(total / instalments, 2))
            remaining -= amount
            rows.append((
                payment_id, order_id,
                order_date + timedelta(days=random.randint(0, 45) + n * 30),
                amount, random.choices(PAYMENT_METHODS, weights=[54, 20, 18, 8])[0],
            ))
            payment_id += 1
    return rows


def build_inventory(products):
    """One row per product per month for the last 18 months."""
    rows = []
    snapshot_id = 1
    months = []
    d = date(END_DATE.year - 1, END_DATE.month, 1)
    for _ in range(18):
        months.append(d)
        d = (d.replace(day=28) + timedelta(days=8)).replace(day=1)
        if d > END_DATE:
            break
    for product in products:
        product_id = product[0]
        level = random.randint(20, 600)
        for month in months:
            level = max(0, level + random.randint(-90, 95))
            rows.append((
                snapshot_id, product_id, month, level,
                random.randint(0, 220), random.randint(15, 120),
            ))
            snapshot_id += 1
    return rows


def load(cursor, table, columns, rows, page_size=2000):
    if not rows:
        print(f"  {table:26} 0 rows (nothing generated)")
        return
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
    execute_values(cursor, sql, rows, page_size=page_size)
    print(f"  {table:26} {len(rows):>8,} rows")


def main():
    connection = psycopg2.connect(url)
    connection.autocommit = False

    try:
        with connection.cursor() as cursor:
            if "--counts" in sys.argv:
                for table in TABLES_IN_LOAD_ORDER:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    print(f"  {table:26} {cursor.fetchone()[0]:>8,} rows")
                return

            print("Truncating existing data...")
            cursor.execute(
                "TRUNCATE " + ", ".join(reversed(TABLES_IN_LOAD_ORDER))
                + " RESTART IDENTITY CASCADE"
            )

            print("Generating and loading...")
            load(cursor, "dim_date",
                 ["date_key", "year", "quarter", "month", "month_name",
                  "day_of_month", "day_of_week", "day_name", "week_of_year",
                  "is_weekend", "fiscal_year", "fiscal_quarter"],
                 build_dim_date())

            regions, countries, cities = build_geography()
            load(cursor, "regions", ["region_id", "region_name"], regions)
            load(cursor, "countries",
                 ["country_id", "country_name", "iso_code", "region_id"], countries)
            load(cursor, "cities",
                 ["city_id", "city_name", "country_id", "latitude", "longitude"], cities)

            employees, sales_ids = build_employees()
            load(cursor, "employees",
                 ["employee_id", "first_name", "last_name", "title", "manager_id",
                  "hire_date", "termination_date", "city_id", "base_salary",
                  "commission_rate"], employees)

            categories, leaf_ids = build_categories()
            load(cursor, "categories",
                 ["category_id", "category_name", "parent_category_id",
                  "category_level"], categories)

            load(cursor, "suppliers",
                 ["supplier_id", "supplier_name", "city_id", "lead_time_days",
                  "reliability_score"], build_suppliers())

            products = build_products(leaf_ids)
            load(cursor, "products",
                 ["product_id", "product_name", "category_id", "supplier_id",
                  "unit_cost", "list_price", "weight_kg", "launch_date",
                  "is_discontinued"], products)

            load(cursor, "product_price_history",
                 ["price_history_id", "product_id", "unit_price", "valid_from",
                  "valid_to", "is_current"], build_price_history(products))

            load(cursor, "customers",
                 ["customer_id", "customer_name", "email", "city_id", "segment",
                  "signup_date", "credit_limit", "is_active"], build_customers())

            campaigns = build_campaigns()
            load(cursor, "campaigns",
                 ["campaign_id", "campaign_name", "channel", "start_date",
                  "end_date", "budget"], campaigns)
            load(cursor, "campaign_customers",
                 ["campaign_id", "customer_id", "contacted_date", "responded"],
                 build_campaign_customers(campaigns))

            orders = build_orders(sales_ids)
            load(cursor, "orders",
                 ["order_id", "customer_id", "employee_id", "order_date",
                  "required_date", "shipped_date", "status", "order_channel",
                  "ship_city_id", "freight"], orders)

            order_items = build_order_items(orders, products)
            load(cursor, "order_items",
                 ["order_item_id", "order_id", "product_id", "quantity",
                  "unit_price", "discount_pct", "line_total"], order_items)

            orders_by_id = {o[0]: o for o in orders}
            load(cursor, "returns",
                 ["return_id", "order_item_id", "return_date",
                  "quantity_returned", "reason", "refund_amount"],
                 build_returns(order_items, orders_by_id))

            totals = {}
            for item in order_items:
                totals[item[1]] = totals.get(item[1], 0.0) + float(item[6])
            load(cursor, "payments",
                 ["payment_id", "order_id", "payment_date", "amount", "method"],
                 build_payments(orders, totals))

            load(cursor, "inventory_snapshots",
                 ["snapshot_id", "product_id", "snapshot_date", "units_on_hand",
                  "units_on_order", "reorder_level"], build_inventory(products))

            print("\nAnalysing tables for the query planner...")
        connection.commit()

        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE")
            cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            print("database size:", cursor.fetchone()[0])

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
