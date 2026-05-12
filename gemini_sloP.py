from playwright.sync_api import sync_playwright
import json

def fetch_all_tcgplayer_listings(product_id):
    # The API endpoint identified in the HAR file
    url = f"https://mp-search-api.tcgplayer.com/v1/product/{product_id}/listings"
    
    # Headers mimicking the browser request from the HAR file
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0"
    }
    
    all_listings = []
    offset = 0
    size = 50 # Fetching 50 listings per request
    
    with sync_playwright() as p:
        # We use an APIRequestContext for direct HTTP requests without loading a full browser page
        request_context = p.request.new_context()
        
        while True:
            # Payload replicated from the HAR file, dynamically updating 'from' and 'size'
            payload = {
                "filters": {
                    "term": {"sellerStatus": "Live", "channelId": 0},
                    "range": {"quantity": {"gte": 1}},
                    "exclude": {"channelExclusion": 0}
                },
                "from": offset,
                "size": size,
                "sort": {"field": "price+shipping", "order": "asc"},
                "context": {"shippingCountry": "US", "cart": {"packages": {}}},
                "aggregations": ["listingType"]
            }
            
            print(f"Fetching listings {offset} to {offset + size}...")
            response = request_context.post(url, headers=headers, data=payload)
            
            if not response.ok:
                print(f"Failed to fetch: {response.status} {response.status_text}")
                break
                
            data = response.json()
            
            # Defensive check to ensure the expected JSON structure exists
            if "results" not in data or not data["results"]:
                break
                
            # The listings are nested inside the first result object
            result_set = data["results"][0]
            listings = result_set.get("results", [])
            
            if not listings:
                break
                
            all_listings.extend(listings)
            
            # If the API returns fewer listings than our size limit, we've reached the last page
            if len(listings) < size:
                break
                
            # Increment the offset for the next page
            offset += size
            
    return all_listings

def extract_key_chars(raw_listings):
    """Extracts and formats the relevant fields from the raw API response.
        Can always come back and add more fields as desired when implementing settings"""
    cleaned_listings = []
    for item in raw_listings:
        try:
            parsed_seller = {
                "price": item.get("price"),
                "shipping": item.get("shippingPrice"),
                "shipping_deal": item.get("sellerShippingPrice"),
                "seller": item.get("sellerName"),
                "verifiedSeller": item.get("verifiedSeller"),
                "condition": item.get("condition"),
                "sku": int(item.get("productConditionId")),
                "sellerKey": item.get("sellerKey"),
                "title": item.get("title", "No Picture Linked"),
                "customListingKey": item.get("linkId", "No Picture Linked")
            }
        except KeyError as e:
            print(f"Missing expected field in listing: {e}")
            continue
        cleaned_listings.append(parsed_seller)
    return cleaned_listings

if __name__ == "__main__":
    # listings = fetch_all_tcgplayer_listings(46466) # Mew (SI)
    # listings = fetch_all_tcgplayer_listings(46475) # primeape (SI) with picture seller listing
    # listings = fetch_all_tcgplayer_listings(571552) # Charizard Vstar (with alt language listings)
    # listings = fetch_all_tcgplayer_listings(478090) # Charizard V Crown Zenith (lots of listings)
    listings = fetch_all_tcgplayer_listings(683673) # Ninja Spinner Greninja (free shipping over X sellers)
    print(f"\nSuccessfully extracted {len(listings)} total listings.")
    
    if listings:
        print("\n--- Example Data for the First Listing ---")
        # Print the all listings for the card nicely formatted
        for listing in listings:
            print(json.dumps(listing, indent=2))