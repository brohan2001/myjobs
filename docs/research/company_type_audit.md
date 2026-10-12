# Company Type Audit

Audit conducted for `data/companies.csv` per DECISIONS D21 and the taxonomy defined in `src/company_type.py` (startup, product, mnc, gcc, services, nonprofit, government).

## Changes Summary

Total changes: 22

| Old Type | New Type | Count |
| :--- | :--- | :--- |
| `""` (empty) | `product` | 3 |
| `""` (empty) | `startup` | 1 |
| `startup` | `product` | 2 |
| `startup` | `gcc` | 1 |
| `product` | `gcc` | 4 |
| `mnc` | `product` | 2 |
| `mnc` | `services` | 8 |
| `services` | `product` | 1 |

## Audit Table

| Slug | Name | Old Type | New Type | Reason |
| :--- | :--- | :--- | :--- | :--- |
| `alphasense-india` | AlphaSense India | `product` | `gcc` | Foreign company captive India centre (GCC in Pune) of US market intelligence firm AlphaSense. |
| `athletics-baseball-operations` | Athletics - Baseball Operations | `""` | `product` | Oakland Athletics MLB baseball franchise operations, filled empty tag matching registry sports team tagging. |
| `athletics-business-operations` | Athletics - Business Operations | `""` | `product` | Oakland Athletics MLB business operations, filled empty tag matching registry sports team tagging. |
| `atlassian` | Atlassian | `mnc` | `product` | Established enterprise collaboration software product company (explicitly listed under product in brief definitions). |
| `bluevine-india` | Bluevine - India | `startup` | `gcc` | Foreign company captive India engineering centre (GCC in Bengaluru) of US fintech company Bluevine. |
| `bswift-india` | bswift India | `product` | `gcc` | Foreign company captive India technology centre (GCC in Bengaluru) of US benefits platform bswift. |
| `cleo-india` | Cleo (India) | `product` | `gcc` | Foreign company captive India development centre (GCC in Bengaluru) of US integration software provider Cleo. |
| `cognizant` | Cognizant | `mnc` | `services` | Major global IT services, consulting, and outsourcing firm, matching peer classification of Infosys, TCS, and Wipro. |
| `detroit-lions` | Detroit Lions | `services` | `product` | NFL professional sports franchise, misclassified as services (consistent with Florida Panthers and Seattle Sounders). |
| `fis-amount` | FIS® Amount™ | `startup` | `product` | Enterprise banking software product of Fortune 500 company FIS (Fidelity National Information Services), not a startup. |
| `globant` | Globant | `mnc` | `services` | Digital IT services and software development consultancy, matching peer classification of Endava. |
| `investors-community-bank` | Investors Community Bank | `mnc` | `product` | Local Wisconsin community bank with ~100 employees, misclassified as a multinational corporation. |
| `luxoft` | Luxoft | `mnc` | `services` | Global IT services and custom software engineering firm (DXC Technology subsidiary). |
| `ntt-data-europe-latam-branch-in-usa-inc` | NTT DATA, Europe & LATAM, Branch in USA, Inc. | `mnc` | `services` | Global IT services, systems integration, and business consulting giant (NTT DATA). |
| `paypay-india` | PayPay India | `product` | `gcc` | Foreign company captive India development centre (GCC in Gurugram) of Japanese payment firm PayPay. |
| `prime` | Prime | `""` | `startup` | Early-stage venture-backed technology startup hiring via Ashby, filling empty tag. |
| `reply` | Reply | `mnc` | `services` | Global IT systems integration and consulting firm, matching peer classification of Endava and Globant. |
| `revolut` | Revolut | `startup` | `product` | Established global digital banking and fintech product platform with >10,000 employees (explicitly cited in brief). |
| `spark` | Spark | `""` | `product` | Established online dating product and platform company (Spark Networks), filling empty tag. |
| `sword-group` | Sword Group | `mnc` | `services` | Specialized IT services, consulting, and digital transformation provider. |
| `tech-mahindra` | Tech Mahindra | `mnc` | `services` | Major Indian IT services and consulting provider, matching peer taxonomy of Infosys and TCS. |
| `thoughtworks-new` | ThoughtWorks_new | `mnc` | `services` | Global software consultancy and custom software delivery services provider. |
