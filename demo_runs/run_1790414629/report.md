# Prospector run report: run_1790414629

**Goal:** Find 15 physiotherapy clinics in Pune that would benefit from an AI phone receptionist
**Status:** done
**Final answer:** Identified and screened physiotherapy clinics in Pune for AI receptionist suitability. Enriched, scored, wrote hooks, and prepared demo receptionists for the top qualifying clinics including Happy Medicare and The Devine Sparsh Physio.

## Plan
1. Search for physiotherapy clinics and rehabilitation centers in Pune.
1. Extract business details including phone numbers, websites, and office hours.
1. Screen clinics that could benefit from an AI receptionist (e.g., missed calls during peak therapy hours, appointment booking needs).
1. Compile and verify contact information for 15 qualified leads.

## Steps
| # | action | ok | observation |
|---|--------|----|-------------|
| 1 | geocode | yes | geocoded 'Pune' to bbox=(18.3614,73.6945,18.6814,74.0145) |
| 2 | search_businesses | no | error: OSMError: Overpass query exceeded its 90s budget. Last error: HTTPSConnectionPool(host='overpass.kumi.systems', port=443): Read timed out. (read timeout=60) |
| 3 | search_businesses | yes | found 5 businesses, 5 new (total leads: 5) |
| 4 | widen_area | yes | widened bbox by factor 1.5: (18.2814,73.6145,18.7614,74.0945) |
| 5 | search_businesses | no | error: OSMError: Overpass query exceeded its 90s budget. Last error: HTTPSConnectionPool(host='overpass.kumi.systems', port=443): Read timed out. (read timeout=60) |
| 6 | geocode | yes | geocoded 'Kothrud, Pune' to bbox=(18.4920,73.7841,18.5224,73.8275) |
| 7 | search_businesses | yes | found 0 businesses, 0 new (total leads: 5) |
| 8 | geocode | yes | geocoded 'Baner, Pune' to bbox=(18.5390,73.7645,18.5790,73.8045) |
| 9 | search_businesses | no | error: OSMError: Overpass query exceeded its 90s budget. Last error: HTTPSConnectionPool(host='overpass.kumi.systems', port=443): Read timed out. (read timeout=60) |
| 10 | geocode | yes | geocoded 'Kothrud, Pune' to bbox=(18.4920,73.7841,18.5224,73.8275) |
| 11 | search_businesses | yes | found 0 businesses, 0 new (total leads: 5) |
| 12 | geocode | yes | geocoded 'Shivajinagar, Pune' to bbox=(18.5276,73.8463,18.5376,73.8563) |
| 13 | search_businesses | yes | found 0 businesses, 0 new (total leads: 5) |
| 14 | enrich | yes | enriched 5 leads |
| 15 | score | yes | scored 5 leads using 0 learned rule(s) |
| 16 | write_hooks | yes | wrote 5 hook(s) |
| 17 | prepare_receptionists | yes | prepared 3 receptionist(s) |
| 18 | finish | yes | run finished |

## Top leads (5 of 5)
| score | name | niche | phone | reasons |
|-------|------|-------|-------|---------|
| 70 | Happy Medicare | physio | +91 20 2729 7631;+91 20 2729 7632;+91 1800 2700 609 | has_phone: +30; no_online_booking: +20; no_chat_widget: +10; limited_hours: +5; site_ok: +5 |
| 20 | The Devine Sparsh Physio | physio | +919226342712 | has_phone: +30; no_website: -10 |
| 0 | Midas | physio | - | limited_hours: +5; no_website: -10 |
| 0 | FlexifyMe | physio | - | no_website: -10 |
| 0 | Advanced Physiotherapy | physio | - | no_website: -10 |

## What was learned from memory
(no learned rules yet)

## What was NOT found
- 3 searches in a row found no new businesses; stopping the search
- fell short of target_count: found 5 of 15
