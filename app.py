import secrets
import datetime
import json
from flask import Flask, render_template, jsonify, request
from flask_simple_crypt import SimpleCrypt
from flask_bootstrap import Bootstrap4
from flask_sqlalchemy import SQLAlchemy
#from flask_htpasswd import HtPasswdAuth



from openai import OpenAI
import genform as gf
import delform as df
import chatform as cf

### Werte aus der user_config.json
API_KEY= ""
GPT_MODEL = ""
LINK = ""
DEL_WINDOW = 7
###

TOKEN_LEN = 32
SQL_PATH = "sqlite:///gpt.db"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'diesen key bitte ändern'
app.config['SQLALCHEMY_DATABASE_URI'] = SQL_PATH

bootstrap = Bootstrap4(app)
cipher = SimpleCrypt()
cipher.init_app(app)
db = SQLAlchemy(app)

class Link(db.Model):
    __tablename__ = 'link'
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String, nullable=False)
    token_master = db.Column(db.String, nullable=False)
    token = db.Column(db.String, nullable=False)
    context = db.Column(db.String)
    time = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    def __init__(self, api_key=None, token=None, token_master=None, context=context, time=None):
        self.api_key = api_key
        self.token = token
        self.token_master = token_master
        self.context = context
        self.time = time

with app.app_context():
    db.drop_all()
    db.create_all()
    with open("config/user_config_sbs.json", 'r') as file:
        config = json.load(file)
        API_KEY = config['API_KEY']
        GPT_MODEL = config['GPT_MODEL']
        LINK = config['LINK']
        DEL_WINDOW = config['DEL_WINDOW']


@app.route("/", methods=('GET','POST'))
def index():
    return render_template('index.html')

@app.route("/delete.html", methods=('GET','POST'))
def delete():
    form = df.DelForm()
    data = " "

    if form.validate_on_submit():

        try:
            ####################################
            # Lösche Links mit Token
            token = form.token.data.strip()
            status = db.session.query(Link).filter(Link.token_master.like(token))
            cnt = status.count()
            status.delete()
            db.session.commit()
            data = "Anzahl gelöschter Links:  " + str(cnt)
            ####################################
            # Lösche alte Daten
            too_old = datetime.datetime.today() - datetime.timedelta(days=DEL_WINDOW)
            status = db.session.query(Link).filter(Link.time < too_old)
            cnt_old = status.count()
            status.delete()
            db.session.commit()
            print("Alte Daten gelöscht: " + str(cnt_old))
            ####################################
        except:
            data = "Fehler beim Löschen der Daten. Bitte versuchen Sie es erneut."
        else:
            data = "Anzahl gelöschter Links:  " + str(cnt)
    return render_template('delete.html', form=form, data=data)

@app.route('/generator.html', methods=('GET','POST'))
def generator():
    form = gf.GenForm()
    data = "Bitte die Daten oben eingeben. Im Anschluss wird die API-Key überrpüft"

    if form.validate_on_submit():
        link = " "
        api_key = API_KEY #form.api_key.data.strip()
        context = form.context.data.strip()

        try:
            client = OpenAI(api_key=api_key)
            completion = client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": "Antorte mit 'Hallo', wenn du das liest."
                    },
                ],
            )
            print(completion.choices[0].message.content)
        except:
            data = "API-Key konnte nicht verifiziert werden. Bitte überprüfen Sie den Key und versuchen Sie es erneut."
        else:
            token_master = secrets.token_urlsafe(TOKEN_LEN)

            try:
                token = secrets.token_urlsafe(TOKEN_LEN)

                link = LINK + token + ".html"

                db.session.add(Link(cipher.encrypt(api_key.encode()), token, token_master, context))

                db.session.commit()
            except:
                data = "Fehler beim Speichern der Daten. Bitte versuchen Sie es erneut."
            else:
                data = "API-Key wurde erfolgreich überprüft. Bitte speichern Sie den Token, um den Link für die Schülerinnen und Schüler später zu löschen. Andernfalls wird der Link nach sieben Tagen gelöscht. Der Token für den Link lautet: " + token_master

            return render_template('generator.html', form=form, data=data, link=link)

    return render_template('generator.html', form=form, data=data)

@app.route('/get_messages', methods=['POST'])
def get_messages():
    print("ssss")
    msg = [{"message": "Hallo", "timestamp": "2023-11-20 12:00"},
            {"message": "Wie geht's?", "timestamp": "2023-11-20 12:01"}]
    return jsonify(msg)

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    message = data['message']

    chat_items = None
    api_key = None
    context = None
    for item in message:
        if 'chat' in item:
            chat_items = item['chat']
        elif 'token' in item:
            api_key = item['token']
            api_key = cipher.decrypt(api_key.encode()).decode()
        elif 'context' in item:
            context = item['context']
    #print("chat: ", chat_items)
    #print("cont: ", context)
    #print("api: ", api_key)

    msg = [{"role": "system", "content": context}]

    if chat_items is not None:
        for chat_item in chat_items:
            if 'user' in chat_item:
                print("User sagt:", chat_item['user'])
                msg.append({"role": "user", "content": chat_item['user']})
            if 'bot' in chat_item:
                print("Bot antwortet:", chat_item['bot'])
                msg.append({"role": "assistant", "content": chat_item['bot']})

    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(model=GPT_MODEL,messages=msg)
    ret = completion.choices[0].message.content


    print("xxxxxxxxxxxxx")
    print(message)
    print("xxxxxxxxxxxxx")

    return jsonify({"status": message, "last": ret})


@app.route('/<name>', methods=('GET','POST'))
def student(name=None):
    data = " "
    token = name.replace('.html', '')

    status = db.session.query(Link).filter(Link.token.like(token))
    cnt = status.count()

    if cnt == 1:
        form = cf.ChatForm()
        l = status.one()
        api_key = l.api_key.decode()

        context = l.context

        data = [{"role": "system",
                "content": context},
                {"role": "last",
                 "content": "---"},
               {"role": "token",
                "content": api_key}]


        return render_template('chat.html', form=form, data=data, context=context, token=api_key)
    else:
        return render_template('error.html')


if __name__ == '__main__':
    app.run()
