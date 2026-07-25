# Name-order conventions for claimant intake

For VCF registration we store names in Western order — **given name(s) first, family name last** — because the VCF.gov portal and most U.S. government forms expect `First Name` / `Last Name`. However, many claimants write their names in the opposite order on intake questionnaires, medical records, and correspondence.

This document lists the conventions ACP-VCF should recognize.

## Surname-first (family name written first)

| Country / region | Example (as written) | Family name | Given name | Notes |
|------------------|----------------------|-------------|------------|-------|
| China (Mainland, Taiwan, Hong Kong, Macau) | Chen Weiming | Chen | Weiming | Mandarin/Cantonese romanizations often join given names: `Wei-Ming`, `Weiming`, or `Wei Ming`. |
| Vietnam | Nguyễn Văn A | Nguyễn | Văn A | Vietnamese names are almost always surname-first; middle name is common. |
| Korea (North & South) | Kim Min-jae | Kim | Min-jae | Romanizations vary: `Minjae`, `Min-jae`, `Min Jae`. |
| Hungary | Nagy István | Nagy | István | One of the few European surname-first cultures. |
| Japan | Tanaka Hiroshi | Tanaka | Hiroshi | Modern Japanese often Westernizes order (Hiroshi Tanaka), especially in English contexts; older records may be surname-first. |
| Mongolia | Batbold Erdene | Batbold | Erdene | Surname-first in official Mongolian; sometimes reversed in English. |
| Cambodia | Sophea Dara | Sophea | Dara | Surname-first is common. |
| Laos | Phimmachanh Bounnhang | Phimmachanh | Bounnhang | Surname-first is common. |

## Given-name-first (Western order)

| Country / region | Example | Family name | Notes |
|------------------|---------|-------------|-------|
| United States, Canada, UK, Australia, New Zealand | John Smith | Smith | Default assumption for the VCF portal. |
| Most of Western Europe (Germany, France, Italy, Spain, etc.) | Pierre Durand | Durand | Given-first. |
| India (most languages) | Rajesh Kumar | Kumar | Given-first in English documents; patronymics may appear as middle names. |
| Philippines | Juan dela Cruz | dela Cruz | Given-first. |
| Thailand | Somchai Jaidee | Jaidee | Given-first in English, though Thai official order can differ. |
| Russia / Ukraine / Belarus | Ivan Petrov | Petrov | Given-first in English/Russian; patronymic is middle name. |
| Middle East / Arabic-speaking countries | Omar Al-Farsi | Al-Farsi | Given-first; family name often begins with `Al-`. |
| Latin America | Carlos García | García | Given-first; often two given names and two surnames. |
| Africa (most regions) | Emmanuel Okafor | Okafor | Given-first in English/French documents. |

## Special cases

- **Spanish- and Portuguese-speaking claimants** often have two family names (paternal and maternal). The VCF portal only has one `Last Name` field, so we generally use the paternal surname and note the second surname in `notes`.
- **Mononymous names** (one name only) are common in some cultures and after migration. In that case the single name goes in `First Name` and `Last Name` is left empty with a review warning.
- **Uncertain order**: when the document does not make the order clear, ACP-VCF flags the name for review rather than guessing.

## How ACP-VCF handles this

1. OCR / Claude Vision extracts the full romanized name and classifies `name_order` as `surname_first` or `given_first`.
2. The backend normalizes to Western order for storage and VCF prep (`first_name` = given name, `last_name` = family name).
3. The prep sheet and case binder display names in Western order, matching what the paralegal pastes into VCF.gov.
4. A `Name order` selector in the manual-entry form lets staff swap first/last if the source document is surname-first.
