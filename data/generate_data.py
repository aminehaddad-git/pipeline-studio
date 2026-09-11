"""
generate_data.py
────────────────────────────────────────────────────────────────────────
Generation of the synthetic banking dataset used by the platform.

No production data may be used for confidentiality reasons, so the data
is generated with four properties that make it realistic enough for the
analytical and predictive modules to be validated:

  1. referential coherence  : every account belongs to an existing client,
                              every transaction concerns an existing account
  2. temporal coherence     : a transaction never precedes the opening of
                              the account it concerns
  3. trend                  : activity grows over the period
  4. seasonality            : December peak, August trough

Produces four CSV files ready to be imported into the staging area.
────────────────────────────────────────────────────────────────────────
"""

import csv
import random
from datetime import date, timedelta
from faker import Faker

fake = Faker("fr_FR")
Faker.seed(7)
random.seed(7)

# ─── Reference data ──────────────────────────────────────────────────
CITIES = ["Tunis", "Sfax", "Sousse", "Bizerte", "Monastir",
          "Gabes", "Kairouan", "Nabeul", "Ariana", "Gafsa"]

CITY_REGION = {"Tunis": "Nord",   "Bizerte": "Nord",   "Ariana": "Nord",
               "Nabeul": "Nord",  "Sfax": "Sud",       "Gabes": "Sud",
               "Gafsa": "Sud",    "Sousse": "Centre",  "Monastir": "Centre",
               "Kairouan": "Centre"}

ACCOUNT_TYPES = ["Courant", "Epargne"]
STATUSES      = ["Actif", "Actif", "Actif", "Inactif"]      # about 75 % active
OPERATIONS    = ["Virement", "Retrait", "Depot", "Paiement"]

# Seasonal coefficient of each month: December peaks, August drops
SEASON = {1: 1.02, 2: 0.92, 3: 0.98,  4: 1.00,  5: 1.04,  6: 1.06,
          7: 1.12, 8: 0.88, 9: 1.02, 10: 1.00, 11: 1.05, 12: 1.22}

START = date(2023, 7, 1)
END   = date(2026, 6, 30)
TOTAL_DAYS = (END - START).days

N_CLIENTS  = 300
N_ACCOUNTS = 450
BASE_VOLUME = 55        # transactions in the first month
GROWTH      = 1.021     # about +2.1 % per month


# ═════════════════════════════════════════════════════════════════════
#  1. CLIENTS
# ═════════════════════════════════════════════════════════════════════
clients = []
for i in range(N_CLIENTS):
    clients.append({
        "id_client":      f"C{2000 + i}",
        "nom":            fake.last_name(),
        "prenom":         fake.first_name(),
        "date_naissance": fake.date_of_birth(minimum_age=18,
                                             maximum_age=80).strftime("%Y-%m-%d"),
        "ville":          random.choice(CITIES),
        "solde":          round(random.uniform(200, 120000), 2),
    })


# ═════════════════════════════════════════════════════════════════════
#  2. BRANCHES  (one per city)
# ═════════════════════════════════════════════════════════════════════
branches = []
for i, city in enumerate(CITIES):
    branches.append({
        "id_agence":  f"AG{200 + i}",
        "nom_agence": f"BIAT {city}",
        "ville":      city,
        "region":     CITY_REGION[city],
        "telephone":  f"7{random.randint(1000000, 9999999)}",
    })


# ═════════════════════════════════════════════════════════════════════
#  3. ACCOUNTS
#     Opening dates are skewed towards recent dates, which reproduces
#     the growth of the portfolio observed in a developing institution.
# ═════════════════════════════════════════════════════════════════════
opening_dates = []
for _ in range(N_ACCOUNTS):
    skew = random.random() ** 0.72          # exponent < 1 pushes towards the end
    opening_dates.append(START + timedelta(days=int(skew * TOTAL_DAYS)))
opening_dates.sort()

accounts = []
for i in range(N_ACCOUNTS):
    accounts.append({
        "id_compte":      f"CPT{3000 + i}",
        "id_client":      f"C{2000 + random.randint(0, N_CLIENTS - 1)}",
        "type_compte":    random.choice(ACCOUNT_TYPES),
        "date_ouverture": opening_dates[i].strftime("%Y-%m-%d"),
        "solde":          round(random.uniform(0, 150000), 2),
        "statut":         random.choice(STATUSES),
    })

account_opened_on = {a["id_compte"]: date.fromisoformat(a["date_ouverture"])
                     for a in accounts}


# ═════════════════════════════════════════════════════════════════════
#  4. TRANSACTIONS
#     Monthly target volume = base x growth^month x seasonal coefficient,
#     perturbed by a random noise, then spread over the accounts that
#     are already open at that date.
# ═════════════════════════════════════════════════════════════════════
months = []
cursor = date(START.year, START.month, 1)
while cursor <= END:
    months.append(cursor)
    cursor = date(cursor.year + (cursor.month // 12),
                  (cursor.month % 12) + 1, 1)

transactions = []
tid = 5000

for index, month in enumerate(months):
    # ── target volume of the month: trend x seasonality x noise ──
    target = BASE_VOLUME * (GROWTH ** index) * SEASON[month.month]
    target = max(5, int(random.gauss(target, target * 0.09)))

    next_month = date(month.year + (month.month // 12),
                      (month.month % 12) + 1, 1)
    last_day = min(next_month - timedelta(days=1), END)

    # ── only the accounts already open may be used ──
    eligible = [a for a in accounts
                if account_opened_on[a["id_compte"]] <= last_day]
    if not eligible:
        continue

    for _ in range(target):
        account = random.choice(eligible)
        earliest = max(month, account_opened_on[account["id_compte"]])
        if earliest > last_day:
            continue
        day = earliest + timedelta(
            days=random.randint(0, (last_day - earliest).days))

        operation = random.choices(OPERATIONS, weights=[30, 28, 24, 18])[0]
        if operation == "Depot":
            amount = random.uniform(100, 12000)
        elif operation == "Retrait":
            amount = random.uniform(20, 3000)
        elif operation == "Virement":
            amount = random.uniform(50, 20000)
        else:
            amount = random.uniform(10, 1500)

        amount = round(amount * (1 + 0.004 * index), 2)   # slight inflation

        transactions.append({
            "id_transaction":   f"TRX{tid}",
            "id_compte":        account["id_compte"],
            "date_transaction": day.strftime("%Y-%m-%d"),
            "montant":          amount,
            "type_operation":   operation,
            "description":      f"{operation} operation",
        })
        tid += 1

transactions.sort(key=lambda t: t["date_transaction"])


# ═════════════════════════════════════════════════════════════════════
#  5. WRITING OF THE FILES
# ═════════════════════════════════════════════════════════════════════
def write_csv(filename, rows, columns):
    with open(filename, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename:<28} {len(rows):>5} rows")


print("Generation of the synthetic dataset\n")
write_csv("clients_history.csv", clients,
          ["id_client", "nom", "prenom", "date_naissance", "ville", "solde"])
write_csv("branches_history.csv", branches,
          ["id_agence", "nom_agence", "ville", "region", "telephone"])
write_csv("accounts_history.csv", accounts,
          ["id_compte", "id_client", "type_compte",
           "date_ouverture", "solde", "statut"])
write_csv("transactions_history.csv", transactions,
          ["id_transaction", "id_compte", "date_transaction",
           "montant", "type_operation", "description"])

print(f"\nPeriod covered : {START} to {END}  ({len(months)} months)")