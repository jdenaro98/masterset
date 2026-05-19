The following files are listed with their corresponding inteactions as they were logged in the browser for your research purposes

1. login_action.har: The interaction data as soon as the user enters their credentials and presses the sign in button
2. photo_seller_add.har: The interaction of adding a card to the cart (already initialized) in any anonymous session (not logged in) from a seller that has a photo attached to the listing. This POST request goes to a different API endpoint and also passes different request .json data 
3. post_login_picture_seller.har: The same interaction as #2 but just from a logged in session with a non-anonymous cart initialized
4. post_login_regular_seller_add.har: Adding a card to the cart from a regular non-photo listing seller while in an authenticated/logged in user sessoin
5. regular_seller_add_and_crete_cart.har: Adding a card to the cart (non-initialized) from a non-logged in session (anonymous) that is from a regular seller without a picture listing. This interaction also highlights how the cart is created through the API POST call just prior to the add to cart call
6. anonymous_cart_then_sign_in_with_cart.har: interaction data immediately after signing in from an anonymous session that has an item in the cart to an account that also had items in the cart. Looks like the carts merge.

These files highlight the nuances of the adding to cart interactions in various states of either logged in or not and adding a regular seller or not to the cart. 