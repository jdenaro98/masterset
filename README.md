# Welcome to MasterSet (aka TCGScraper)!!

## Intro

This app is designed to help build master sets efficiently and cheaply by scraping live seller data for requested cards from TCGPlayer's website. It then aggressively optimizes by number of sellers and allows the user to dynamically choose filters, and add to the cart in a native browser window when done!

<details>
  <summary>The extensive back-story behind this is this:</summary>

    I took a trip to Japan and when wandering around Tokyo, we stopped in a random konbini that had some Pokémon packs for sale. At this point, I hadn't touched Pokémon cards since I was a kid and figured why not, even though they're Japanese it would be cool for the nostalgia. This happened to be the release day of the Ninja Spinner set ... although I didn't realize it until after I bought the packs!

    I ripped the 5 packs I bought and hit the Mega Dragalge and was super excited and remembered why this was so fun as a kid. I came home and immediately fell into the rabbit hole that is Pokémon cards today. I rediscovered some good things like people enjoying the cards, the community created because of it, more kids getting back into it and just the pure fun of the game that has been around for so long. I also discovered some of the scars of the hobby that exist today like scalping, weighing packs, re-packing, people using wild techniques to try to identify if a pack has hits and just the sheer disgust that I had for the actions of the few that impact the many. 

    Regardless, in my research I also stumbled upon the VSTAR Universe/Crown Zenith set. I immediately fell in love with some of the art and how different it was from the any other Pokémon card/set I had seen before. The Hisuian Zoroark, the Galarian Moltres, the Thievul and of course the Palkia/Dialga/Giratina/Arceus cards were all so intriguing! I bought some VSTAR Universe packs on eBay and was hooked - I figured I might as well master set. 

    But after realizing that I'd probably go broke in the process of trying to rip my way to a master set I realized it would be way more economical to just buy the singles. But I had a dilemma. I still needed 207 out of the 351 cards and finding all of those on TCGPlayer would not only be tedious, but I'd also waste a bunch of money on shipping because I'd probably end up with 207 different sellers. That's when I found TCG's optimizer ... and how it doesn't work on Pokémon Japan :(

    That's when I decided to make this and add every single automation/helper feature I could to make it as easy as possible for myself to master set and hopefully help anyone else that's in a similar situation. 

    This works regardless of TCG and dynamically pulls data from TCGPlayer's website on every run so you're always getting the freshest data, especially the seller listings. It is limited to sets that have a 'price guide' associated with them so new/old sets or obscure sets from not as popular games won't work. 

</details>

<br>

Thanks for stopping by and happy collecting!

---

## App Flow

### Main page
- Starting the app, you're greeted by a splashcreen and taken to the 'main page'. This lets you enter the main function scraping data by TCG.
    - ** Note ** I'm working on the ability to choose a character from any game to scrape all the existing cards of that character (think collecting all Gengars) and be able to choose the one's you'd like to optimize

### Card Choices and Scraping
- From there, you'll be guided through the flow of selecting a game, a set, and the desired cards from that set
- You can scrape cards from multiple sets if desired
- After finishing card selection, the scraper will do its work and bring you to the Dynamic Optimizer page

### Optimizer
- This is the bread and butter of this tool and what makes it unique! It will optimize all cards from all games/sets without limitations to languages or TCG.
- The optimizer does an aggressive optimization based on minimizing the number of sellers (thus greatly reducing shipping costs in requests with many cards).
- Here is where you can choose which 'cart' you'd like to add to a real TCG Player cart if you'd like!
- You can choose to add either:
    - The baseline 'first listings' cart where it just chose the first (i.e. cheapest) listing on TCG Player for each requested card or ...
    - The Dynamic Cart choice. This defaults to the filters of allowing only 'Near Mint' and 'Lightly Played' cards
        - In the bottom section you can actively adjust filters to see how the dynamic optimizer changes price.
        - When filters get too restrictive, thus preventing any seller listings from matching those conditions, you'll be greeted with warnings below as to which cards didn't meet those criteria and why
- The cheapest cart will be highlighted in green, and pressing enter on your selected cart will give you the option to add these to a cart

### Adding to a Cart and Saving for Later
- The cart create screen will send a bunch of API calls to TCG Player and utilize your native Google Chrome browser to hand over the fully created cart to you! 
- From here you can admire the convenience, edit the cart, add new cards or start over
- Because this is a fully functioning browser window, you'll also be able to log in to your TCG Player account so your cart will be 'saved' across browser sessions
- You can also save these cards for later or even go through with your purchase if you'd like
- ** Note** This app was built with safety, security, and the integrity of your personal information in mind. This is why you don't enter any credentials or payment information in the app at all! Your natively installed Google Chrome browser handles everything after we tell it what to add to the cart so there's no question of your purchase being secure or not! 

## Release Install (Win/MacOS)

Navigate to the release page and install the most recent release for your applicable Operating System! 

## Development/Source code installation

### Dependencies
- Python (for virtual environment)
- Node.js/npm for js dependencies (blessed, Electron)
- Google Chrome (for adding cards to a cart)

### Installation

- After first time installation (below), all you have to do to run the app is to be in your python venv and run ```npm start``` to run the Electron.js app.

- VSCode
    1. Clone Repo using https://github.com/jdenaro98/masterset_tool.git
    2. Open Terminal Using 
        - Ctrl + Shift + `
        - Or Terminal -> New Terminal
    3. Assuming you have python installed, it will automatically open the virtual environment (venv), just give it a second
    4. ```python install -r requirements.txt``` to install python dependencies
    5. ```playwright install``` installs playwright (required to add to a cart)
    6. ```npm install``` to install node dependencies
    7. ```npm start``` to run masterset_tool app

- CLI
    1. Clone the repo using ```git clone https://github.com/jdenaro98/masterset_tool.git```
    2. cd to masterset_tool repo directory
    3. ```python -m venv venv``` to create virtual environment
    4. Mount virtual environment:
        - (Mac) source venv/bin/activate
        - (Win) venv/scripts/activate\
    5. ```python install -r requirements.txt``` to install python dependencies
    6. ```playwright install``` installs playwright (required to add to a cart)
    7. ```npm install``` to install node dependencies (must already have node installed on system)
    8. ```npm start``` to run masterset_tool app