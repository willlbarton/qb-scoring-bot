Set up a virtual environment and install dependencies:

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the project folder with the bot token:

```env
DISCORD_TOKEN=your_bot_token
```

Run the bot (with the virtual environment activated):

```sh
python bot.py
```

Run the tests (with the virtual environment activated):

```sh
python -m unittest discover -s tests -v
```
