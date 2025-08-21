#  TODO
- Starting with a simple role setup. In the future the role configuration could be extended.
    - In the SocialCreditConfig, each role could be set up with it's details and use a lambda that takes
        the user's social credit score and returns True if they are in the group
        roles need a name, permissions.
    - To do this, the channels will also need to be configurable in a simular way and use the role
        objects created in the last step for setting permissions
- Add group setup
    - we will have two roles:
        - good can access all chats, bad can only access bad chat
        - there is soooo much more you can do here like giving good people the ability to manage nicknames or maybe move bad people around in vc
    - two text chats and two voice chats
        - good text/good voice and bad text/bad voice
        - otherwise doesn't effect the rest of the server
    - Add setting roles based on score
        - positive score = you're good,  negative score = you're bad
- every x time period (adjustable) have social credit bot judge the server
    - the bot will give the user a value between -100 and 100 to add to their social credit score
    - everyone's scores will be saved and updated (in a json blob for now)
        - along with a text blurb about the user and their history
        - let the bot know this is the only place he can store history about the user
- Move config to a file (for example, the time period to search)
- Add a field to the data retrieved for each user which provides a short nickname that the user will be assigned.
- Need to implement some checks on the prompt length to make sure we're not sending an invalid request (openrouter will return a 400 Bad Request)