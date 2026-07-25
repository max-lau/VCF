# Name-order conventions for claimant intake

For VCF registration we store names in Western order — **given name(s) first, family name last** — because the VCF.gov portal and most U.S. government forms expect `First Name` / `Last Name`. However, many claimants write their names in the opposite order on intake questionnaires, medical records, and correspondence.

This document lists the conventions ACP-VCF should recognize **as they appear on official or English-language documents** submitted to the firm. Traditional or colloquial usage may differ, but the table below reflects the order a paralegal is likely to see on the paperwork.

## Surname-first (family name written first)

| Country / region | Example (as written) | Family name | Given name | Notes |
|------------------|----------------------|-------------|------------|-------|
| China (Mainland, Taiwan, Hong Kong, Macau) | Chen Weiming | Chen | Weiming | Mandarin/Cantonese romanizations often join given names: `Wei-Ming`, `Weiming`, or `Wei Ming`. |
| Vietnam | Nguyễn Văn A | Nguyễn | Văn A | Vietnamese names are almost always surname-first; middle name is common. |
| Korea (North & South) | Kim Min-jae | Kim | Min-jae | Romanizations vary: `Minjae`, `Min-jae`, `Min Jae`. |
| Japan | Tanaka Hiroshi | Tanaka | Hiroshi | Passports and official Japanese documents are surname-first; English forms may be Westernized to `Hiroshi Tanaka`. |
| Mongolia | Batbold Erdene | Batbold | Erdene | Official Mongolian order is surname-first; often reversed in English. |
| Hungary | Nagy István | Nagy | István | One of the few European surname-first cultures. |
| Cambodia | Sophea Dara | Sophea | Dara | Surname-first is common on official documents. |
| Laos | Phimmachanh Bounnhang | Phimmachanh | Bounnhang | Surname-first is common on official documents. |

## Given-name-first (Western order)

| Country / region | Example | Family name | Notes |
|------------------|---------|-------------|-------|
| United States, Canada, UK, Australia, New Zealand | John Smith | Smith | Default assumption for the VCF portal. |
| Most of Western Europe (Germany, France, Italy, Spain, Netherlands, Belgium, Scandinavia, etc.) | Pierre Durand | Durand | Given-first on passports and IDs. |
| India | Rajesh Kumar | Kumar | Given-first in English official documents; patronymics may appear as middle names. |
| Pakistan, Bangladesh | Ali Hassan | Hassan | Given-first in English official documents. |
| Sri Lanka | Nimal Perera | Perera | Given-first in English official documents. |
| Nepal | Ram Sharma | Sharma | Given-first in English official documents. |
| Philippines | Juan dela Cruz | dela Cruz | Given-first. |
| Thailand | Somchai Jaidee | Jaidee | Given-first in English/romanized official documents. |
| Indonesia | Budi Santoso | Santoso | Given-first on official IDs; many ethnic groups do not use surnames. |
| Malaysia | Ahmad bin Abdullah | Abdullah | Given-first in Malay/English official documents; Chinese Malaysian documents in Chinese may be surname-first. |
| Myanmar / Burma | Kyaw Soe | Soe | Given-first in English official documents. |
| Singapore | Lim Wei Ming | Lim | Given-first in English official documents; Chinese-language documents may be surname-first. |
| Brunei, Timor-Leste | Maria da Costa | da Costa | Given-first. |
| Russia, Ukraine, Belarus | Ivan Petrov | Petrov | Given-first; patronymic is middle name. |
| Middle East / Arabic-speaking countries | Omar Al-Farsi | Al-Farsi | Given-first on passports and IDs; family name often begins with `Al-`, `El-`, `Ben`, `Bin`, etc. |
| Israel | David Cohen | Cohen | Given-first in Hebrew/English official documents. |
| Iran, Afghanistan (Dari/Pashto official docs) | Reza Karimi | Karimi | Given-first on official documents. |
| Turkey | Mehmet Yılmaz | Yılmaz | Given-first (surname-law tradition). |
| Latin America (Mexico, Central America, South America) | Carlos García López | García | Given-first; often two given names and two surnames. Use the paternal surname for `Last Name` unless the client specifies otherwise. |
| Brazil | João Silva Santos | Silva | Given-first; Portuguese naming with multiple surnames. |
| Africa — Anglophone / Francophone / Lusophone | Emmanuel Okafor | Okafor | Given-first in English/French/Portuguese official documents. |
| Ethiopia, Eritrea | Daniel Tadesse | Tadesse | Given-first in Amharic/English official documents. |
| South Africa | Sibusiso Ndlovu | Ndlovu | Given-first in official documents. |

## Regions with mixed or context-dependent order

| Country / region | Typical document order | Notes |
|------------------|------------------------|-------|
| Malaysia | Given-first (Malay/English); surname-first (Chinese-language docs) | Use the language of the source document as the tie-breaker. |
| Singapore | Given-first (English); surname-first (Chinese docs) | Same approach as Malaysia. |
| Hong Kong | Given-first or surname-first | English forms are given-first; Chinese forms are surname-first. |
| Macau | Given-first or surname-first | Portuguese-influenced documents may be given-first; Chinese forms are surname-first. |
| Japan (English forms) | Often Westernized to given-first | Check the document language and field labels. |
| Mongolia (English forms) | Often reversed to given-first | Official Mongolian documents remain surname-first. |

## Special cases

- **Spanish- and Portuguese-speaking claimants** often have two family names (paternal and maternal). The VCF portal only has one `Last Name` field, so use the paternal surname and note the second surname in `notes`.
- **Arabic names** may include a kunya (e.g., `Abu Omar`), nasab (`bin`/`ibn`), and nisba (`Al-Masri`). On passports, the machine-readable zone and name fields are typically given-first, family-name-last.
- **Mononymous names** (one name only) are common in some cultures and after migration. In that case the single name goes in `First Name` and `Last Name` is left empty with a review warning.
- **Uncertain order**: when the document does not make the order clear, ACP-VCF flags the name for review rather than guessing.

## How ACP-VCF handles this

1. OCR / Claude Vision extracts the full romanized name and classifies `name_order` as `surname_first` or `given_first`.
2. The backend normalizes to Western order for storage and VCF prep (`first_name` = given name, `last_name` = family name).
3. The prep sheet and case binder display names in Western order, matching what the paralegal pastes into VCF.gov.
4. A `Name order` selector in the manual-entry form lets staff swap first/last if the source document is surname-first.
5. When `preferred_language` is set to a language associated with surname-first customs (e.g., Chinese, Cantonese, Korean, Japanese, Vietnamese, Mongolian, Khmer, Lao), the UI auto-selects `surname_first`. Staff can still override it.

## Quick-reference: auto-select rules

ACP-VCF treats the following `preferred_language` values as **surname-first**:

- Chinese / Mandarin / Cantonese / 中文 / 粤语
- Korean / 한국어
- Japanese / 日本語
- Vietnamese / Tiếng Việt
- Mongolian / Монгол
- Khmer / ភាសាខ្មែរ
- Lao / ພາສາລາວ

All other values default to **given-first** unless the extraction explicitly returns `name_order: surname_first`.
