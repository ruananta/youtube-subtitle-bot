# Install the  required module using -> pip install -r requirements.txt
import re
import logging
import requests
import urllib
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# ruananta
import openai
# ruananta

##uncomment the comment below when testing bot using .env
from dotenv import load_dotenv
import os

from Addons import db

import tiktoken

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ParseMode,
    utils
)

from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    Filters,
    PicklePersistence,
    CallbackContext
)

from telegram.utils.helpers import escape_markdown

from openai import OpenAI

##uncomment this after filling the .env folder
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s]%(asctime)s - %(message)s"
)
openai_api_key = os.getenv("GPT_API")

client = OpenAI(
    api_key=openai_api_key,  # ваш ключ в VseGPT после регистрации
    base_url="https://api.vsegpt.ru/v1",
)

log = logging.getLogger("YoutubeTranscript")
log.info("\n\n Bot is Starting......")

CHOOSING, SENDING_YOUTUBE_URL, CHOOSING_LANGUAGE, CHOOSING_FORMAT, TRANSLATE, AGE_RISTRICTED, SEND_BROADCAST = range(7)

choose_button = [
    ["👻 Получить субтитры", "ℹ️ Помощь", "👋 Прощай"]
]

choose_button_markup = ReplyKeyboardMarkup(
    choose_button, resize_keyboard=True, One_time_keyboard=True)


def is_url(text):
    youtube_link_pattern = r"(be\/|embed\/|shorts\/|v\/|e\/|a=|v=)([^\/&?\n\r=#\s]*)"
    link = re.search(youtube_link_pattern, text)
    if link:
        return link.group(2)
    return None


def no_of_subtitle(video_id, update, context):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        context.user_data["transcript_list"] = transcript_list
    except Exception as e:
        log.error(e)
        update.message.reply_text("Нет субтитров для этого видео",
                                  reply_markup=choose_button_markup)
        return CHOOSING
    language_button = []
    language_dictionary = {}
    for subtitle in transcript_list:
        language = subtitle.language
        language_code = subtitle.language_code
        if subtitle.language_code == "ru":
            language = "русский"
        elif subtitle.language_code == "en":
            language = "английский"
        if subtitle.is_generated:
            language_dictionary[language] = f'{language_code}_g'
        else:
            language_dictionary[language] = language_code
        button = [InlineKeyboardButton(
            text=language, callback_data=language)]
        language_button.append(button)
    language_button.append(
        [InlineKeyboardButton(text="Translate", callback_data="Translate")])
    return InlineKeyboardMarkup(language_button), language_dictionary


def make_timestamp(time, user_format):
    time = float(time)
    hours, remainder = divmod(time, 3600)
    mins, secs = divmod(remainder, 60)
    ms = int(round((time - int(time)) * 1000, 2))
    secs = int(secs)
    if user_format == "VTT":
        return "{:02.0f}:{:02.0f}:{:02.0f}.{:03d}".format(hours, mins, secs, ms)
    elif user_format == "SRT":
        return "{:02.0f}:{:02.0f}:{:02.0f},{:03d}".format(hours, mins, secs, ms)


def create_file(formated_string, user_format, user_chat_id):
    with open(f"{user_chat_id}.{user_format}", "w", encoding="utf-8") as file:
        file.write(formated_string)


def video_title(video_id):
    params = {"format": "json",
              "url": "https://www.youtube.com/watch?v=%s" % video_id}
    url = "https://www.youtube.com/oembed"
    query_string = urllib.parse.urlencode(params)
    url = url + "?" + query_string
    response = requests.get(url)
    data = response.json()
    return data["title"]


def button_formater(button_list):
    no_of_buttons = len(button_list)
    button_page = {}
    page_no = 1
    for i in range(0, no_of_buttons, 5):
        new_button_list = button_list[i:i + 5]
        new_button_list.append([InlineKeyboardButton(
            text="<<", callback_data="<<"), InlineKeyboardButton(text=">>", callback_data=">>")])
        button_page[page_no] = new_button_list
        page_no += 1

    return button_page, page_no


def start(update: Update, context: CallbackContext):
    update.message.reply_text(text=f"🙋*Привет* {escape_markdown(update.effective_user.first_name, version=2)},\n"
                                   "☑️*Нажми получить субтитры для начала выгрузки субтитров*\n"
                                   "☑️*Нажми Помощь если тебе нужна помощь по данному боту*",
                              reply_markup=choose_button_markup,
                              parse_mode=ParseMode.MARKDOWN_V2)
    chat_id = update.message.chat_id
    if not db.is_added("BOTUSERS", update.message.chat_id):
        db.add_to_db("BOTUSERS", update.message.chat_id)
    if context.user_data.get("returned_data"):
        del context.user_data["returned_data"]
    if context.user_data.get("button_list_markup"):
        del context.user_data["button_list_markup"]
    if context.user_data.get("language_button"):
        del context.user_data["language_button"]
    return CHOOSING


def choosing(update: Update, context: CallbackContext):
    choice_text = update.message.text
    if (choice_text == "Получить субтитры" or choice_text == "👻 Получить субтитры" or choice_text == "получить субтитры"
            or choice_text == "get"):
        update.message.reply_text(
            text="⏩*Пришли мне любую ссылку youtube видео 🔗url которая содержит субтитры\(Mannual/Generated\):*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN_V2)
        return SENDING_YOUTUBE_URL
    if choice_text == "ℹ️ Помощь" or choice_text == "Помощь" or choice_text == "помощь" or choice_text == "help":
        update.message.reply_text(
            text="*Here is 🗒️list of things i can do for you:*\n"
                 "🔍*Extract subtitle from youtube links in different languages*\n"
                 "🔠Translate subtitle of pariticular video in different languages\n\n"
                 "*To extract subtitle follow this step:*\n"
                 "👉_Click on Extract subtitle then give your link of youtube video from which you want to extract subtitle_\n"
                 "👉_Click on available language or click on translate to translate subtitle into the unavaliable language_\n"
                 "🔐_Choose format 'VTT', 'SRT' or TXT \(WITHOUT TIMESTAMP\)\. NO WORD WRAP version of TXT will extract subtitle as paragraph_\n"
                 "🙃Done\n\n"
                 "🔴*ANY PROBLEM?*\n"
                 "👉_Make sure that the video link is valid_\n"
                 "👉_Make sure that the video have subtitle available either mannual or generated_\n"
                 "👉_Make sure that video isn't georestricted_\n"
                 "👉_Make sure that video isn't age restricted_\n\n"
                 "*Didn't find your solution contact @my\_name\_is\_vivek , stating your problem with video link attached which isn't working for you\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )


# MAKING BUTTON TO CHOOSE
format_button = [[InlineKeyboardButton(text='TXT_GPT', callback_data="TXT_GPT")],
                 [InlineKeyboardButton(text="SRT", callback_data="SRT")],
                 [InlineKeyboardButton(text='VTT', callback_data="VTT")],
                 [InlineKeyboardButton(text='TXT (NO TIMESTAMP)', callback_data="TXT")],
                 [InlineKeyboardButton(text='TXT (NO TIMESTAMP) NO WORD WRAP', callback_data="TXT_W")],
                 [InlineKeyboardButton(text="🔙 Back", callback_data="back")]]

format_button_markup = InlineKeyboardMarkup(format_button)


def choosing_language(update: Update, context: CallbackContext):
    user_language = update.callback_query.data
    if user_language == ">>" or user_language == "<<":
        button_list = context.user_data["button_list"]
        page_no = context.user_data.get("page_no")
        if user_language == ">>":
            context.user_data["count"] += 1
            if context.user_data["count"] == page_no:
                context.user_data["count"] = 1
        if user_language == "<<":
            context.user_data["count"] -= 1
            if context.user_data["count"] < 1:
                context.user_data["count"] = page_no - 1
        count = context.user_data.get("count")
        update.callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(button_list[count]))
        return CHOOSING_LANGUAGE
    language_dictionary = context.user_data.get('language_dictionary')
    language = list(language_dictionary.keys())
    video_id = context.user_data.get("video_id")
    context.user_data["language"] = user_language
    selected_language = update.callback_query.message.edit_text(
        "🔠 *language selected*: {} ".format(escape_markdown(user_language, version=2)),
        parse_mode=ParseMode.MARKDOWN_V2)
    context.user_data["selected_language"] = selected_language

    if user_language in language:
        language_code = language_dictionary[user_language]
        check_generated = "_g" in language_code
        if check_generated:
            transcript_list = context.user_data["transcript_list"]
            language_code = language_code.replace("_g", "")
            transcript = transcript_list.find_generated_transcript([language_code])
            returned_data = transcript.fetch()
        else:
            returned_data = YouTubeTranscriptApi.get_transcript(
                video_id, languages=[language_code])
        context.user_data["returned_data"] = returned_data
    else:
        translate_dictionary = context.user_data["translate_dictionary"]
        language_code = translate_dictionary[user_language]
        # fixing the english translation
        notavailable = True
        if user_language == "English":
            try:
                returned_data = YouTubeTranscriptApi.get_transcript(
                    video_id, languages=[language_code])
                context.user_data["returned_data"] = returned_data
                notavailable = False
            except:
                notavailable = True
        if notavailable:
            transcript = context.user_data["transcript"]
            translated_transcript = transcript.translate(f'{language_code}')
            returned_data = translated_transcript.fetch()
            context.user_data["returned_data"] = returned_data

    update.callback_query.message.reply_text(
        text="🧖 *В каком формате вы хотите субтитры?:*",
        reply_markup=format_button_markup,
        parse_mode=ParseMode.MARKDOWN_V2)
    return CHOOSING_FORMAT


def translate(update: Update, context: CallbackContext):
    language_dictionary = context.user_data.get('language_dictionary')
    video_id = context.user_data.get("video_id")
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        transcript = transcript_list.find_transcript(["en"])
    except:
        transcript = transcript_list.find_transcript(
            [f'{list(language_dictionary.values())[0].replace("_g", "")}'])
        pass
    context.user_data["transcript"] = transcript
    translate_list = transcript.translation_languages
    button_list = []
    translate_dictionary = {}
    for i in range(0, len(translate_list), 2):
        language = translate_list[i]["language"]
        language_code = translate_list[i]["language_code"]
        translate_dictionary[language] = language_code
        try:
            language2 = translate_list[i + 1]["language"]
            language_code2 = translate_list[i + 1]["language_code"]
            translate_dictionary[language2] = language_code2
            translate_button = [InlineKeyboardButton(text=language, callback_data=language), InlineKeyboardButton(
                text=language2, callback_data=language2)]
        except IndexError:
            translate_button = [InlineKeyboardButton(
                text=language, callback_data=language)]
        button_list.append(translate_button)
    button_list, page_no = button_formater(button_list)
    button_list_markup = InlineKeyboardMarkup(button_list[1])
    context.user_data["translate_dictionary"] = translate_dictionary
    context.user_data["button_list"] = button_list
    context.user_data["page_no"] = page_no
    context.user_data["button_list_markup"] = button_list_markup
    context.user_data["count"] = 1
    update.callback_query.message.edit_text(
        text="⌨️ *Choose the language in which your want your subtitle to 🔄convert:*",
        reply_markup=button_list_markup,
        parse_mode=ParseMode.MARKDOWN_V2)
    return CHOOSING_LANGUAGE


def choosing_format(update: Update, context: CallbackContext):
    user_format = update.callback_query.data
    returned_data = context.user_data.get("returned_data")
    if user_format == "back":
        selected_language = context.user_data.get("selected_language")
        selected_language.delete()
        language_button = context.user_data.get("language_button")
        update.callback_query.message.edit_text(
            text="*⏬Выбери доступный язык или нажми на кнопку перевод, для автоматического перевода на другой язык:*",
            reply_markup=language_button,
            parse_mode=ParseMode.MARKDOWN_V2)
        return CHOOSING_LANGUAGE
    user_chat_id = update.callback_query.message.chat_id
    Display_format = user_format.replace("_W", "").replace("_GPT", "")
    bot_message = update.callback_query.message.edit_text(
        text=f"*Format: {Display_format}\n\n🟢Твои субтитры готовы:*",
        parse_mode=ParseMode.MARKDOWN_V2)
    text_formatted = ""
    lines = []
    # MAKING TIMESTAMP
    for i, line in enumerate(returned_data):
        if user_format == "TXT_W":
            line = line['text'].replace("\n", " ")
            text_formatted = text_formatted + line + " "
            continue
        end = line['start'] + line['duration']
        time_text = "{} --> {}".format(
            make_timestamp(line["start"], user_format),
            make_timestamp(
                returned_data[i + 1]['start']
                if i < len(returned_data) - 1 and returned_data[i + 1]['start'] < end else end,
                user_format)
        )
        if user_format == "VTT":
            lines.append("{}\n{}".format(time_text, line['text']))
        elif user_format == "SRT":
            lines.append(
                str(i + 1) + '\n' + "{}\n{}".format(time_text, line['text']))
    if user_format == "TXT":
        text_formatted = TextFormatter().format_transcript(returned_data)
        create_file(text_formatted, 'txt', user_chat_id)
    # ruananta
    if user_format == "TXT_GPT":
        text_formatted = TextFormatter().format_transcript(returned_data)
        text_formatted = format_to_chatgpt(text_formatted)
        create_file(text_formatted, 'txt_gpt', user_chat_id)
    elif user_format == "VTT":
        formated_string = "WEBVTT\n\n" + "\n\n".join(lines) + "\n"
        create_file(formated_string, 'vtt', user_chat_id)
    elif user_format == "SRT":
        formated_string = "\n\n".join(lines) + "\n"
        create_file(formated_string, 'srt', user_chat_id)
    elif user_format == "TXT_W":
        create_file(text_formatted, 'txt', user_chat_id)
        user_format = "TXT"
    video_id = context.user_data.get('video_id')
    my_file_name = video_title(video_id)
    context.bot.send_document(user_chat_id, open(
        f"{user_chat_id}.{user_format.lower()}", "rb"), f"{my_file_name}.{user_format.lower()}",
                              reply_markup=choose_button_markup,
                              caption=f"Сделано в 🧠 \n~by @{bot_message.from_user.username}")
    os.remove(f"{user_chat_id}.{user_format.lower()}")
    if context.user_data.get("returned_data"):
        del context.user_data["returned_data"]
    if context.user_data.get("button_list_markup"):
        del context.user_data["button_list_markup"]
    if context.user_data.get("language_button"):
        del context.user_data["language_button"]
    return CHOOSING

def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "openai/gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
    elif "gpt-4" in model:
        print("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
        return num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens

def format_to_chatgpt(text):
    prompt = "Расставь знаки препинания, проверь орфографию, раздели предложения и абзацы. \n\n" + text
    messages = []
    messages.append({"role": "user", "content": prompt})
    max_tokens = len(prompt.split()) + int(len(prompt.split()) * 0.2)
    try:
        response_big = client.chat.completions.create(
            model="openai/gpt-3.5-turbo-0125",
            messages=messages,
            temperature=0.7,
            n=1,
            max_tokens=4096,  # максимальное число ВЫХОДНЫХ токенов. Для большинства моделей не должно превышать 4096
            extra_headers={"X-Title": "YTTDL"},  # опционально - передача информация об источнике API-вызова
        )
        response_text = response_big.choices[0].message.content
        return response_text
    except Exception as e:
        return str(e)


def sending_youtube_url(update: Update, context: CallbackContext):
    user_text = update.message.text
    video_id = is_url(user_text)
    context.user_data["video_id"] = video_id
    if video_id is None:
        update.message.reply_text(
            text="🚫*Ваша ссылка, похоже, не является ссылкой на видео с YouTube. Пожалуйста, 🕵️‍♀️проверьте 🔗ссылку и попробуйте снова.*",
            reply_markup=choose_button_markup,
            parse_mode=ParseMode.MARKDOWN_V2)
        return CHOOSING
    else:
        button_dictionary = no_of_subtitle(video_id, update, context)
        if button_dictionary == CHOOSING:
            return CHOOSING
        language_button, language_dictionary = button_dictionary
        update.message.reply_text(
            text="*⏬Выберите доступный язык или нажми на кнопку перевод, для автоматического перевода на другой язык:*",
            reply_markup=language_button, parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data["language_button"] = language_button
        context.user_data["language_dictionary"] = language_dictionary
        return CHOOSING_LANGUAGE


def stat(update: Update, context: CallbackContext):
    update.message.reply_text(
        text="*🤖Bot stats*\n\n💚TOTAL USERS: {}".format(len(db.get_all("BOTUSERS"))),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN_V2)


def broadcast(update: Update, context: CallbackContext):
    update.message.reply_text(text=" Send me your the message to broadcast")
    return SEND_BROADCAST


def send_broadcast(update: Update, context: CallbackContext):
    message_type = utils.helpers.effective_message_type(update)
    update.message.reply_text("🔃In progress...")
    users = db.get_all("BOTUSERS")
    done = error = 0
    for i in users:
        try:
            if message_type == 'text':
                msg = update.message.text
                context.bot.send_message(int(i), msg)
            elif message_type == 'photo':
                msg = update.message.photo
                image_caption = update.message.caption
                if image_caption == None:
                    context.bot.send_photo(int(i), msg[-1])
                else:
                    context.bot.send_photo(int(i), msg[-1], caption=image_caption)
            elif message_type == 'video':
                msg = update.message.video
                video_caption = update.message.caption
                if video_caption == None:
                    context.bot.send_video(int(i), msg)
                else:
                    context.bot.send_video(int(i), msg, caption=video_caption)
            elif message_type == 'audio':
                msg = update.message.audio
                audio_caption = update.message.caption
                if audio_caption == None:
                    context.bot.send_audio(int(i), msg)
                else:
                    context.bot.send_audio(int(i), msg, caption=audio_caption)
            elif message_type == 'document':
                msg = update.message.document
                document_caption = update.message.caption
                if document_caption == None:
                    context.bot.send_document(int(i), msg)
                else:
                    context.bot.send_document(int(i), msg, caption=document_caption)
            elif message_type == 'voice':
                msg = update.message.voice
                context.bot.send_voice(int(i), msg)
            elif message_type == 'video_note':
                msg = update.message.video_note
                context.bot.send_video_note(int(i), msg)
            done += 1
        except Exception as e:
            error += 1
            log.exception(e)
    update.message.reply_text("📩 Broadcast completed.\n\n🟩 Success: {}\n🟥 Failed: {}".format(done, error))
    return ConversationHandler.END


def done(update: Update, context: CallbackContext):
    update.message.reply_text(
        text="*Ok see you later, 🥱send me* /start *to wake me*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


def main():
    if os.path.exists("Youtube_link"):
        os.remove("Youtube_link")
    persistence = PicklePersistence(filename="Youtube_link")
    try:
        updater = Updater(token=os.getenv("API_TOKEN"),
                          persistence=persistence)
        dispatcher = updater.dispatcher
        AUTH = [int(i) for i in os.getenv("OWNER").split(" ")]
    except Exception as e:
        log.exception(e)
        exit(1)
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
        ],
        states={
            CHOOSING: [
                MessageHandler(
                    Filters.regex(
                        '^(Получить субтитры|Помощь|👻 Получить субтитры|ℹ️ Помощь|получить субтитры|помощь|get|help)$',
                    ),
                    choosing
                )
            ],
            SENDING_YOUTUBE_URL: [
                MessageHandler(
                    Filters.text & ~(Filters.command |
                                     Filters.regex('^Done$')),
                    sending_youtube_url
                )
            ],
            CHOOSING_LANGUAGE: [
                CallbackQueryHandler(
                    choosing_language, pattern=r'[\w><:]+[^(Translate)]'),
                CallbackQueryHandler(translate, pattern='^Translate$')

            ],
            CHOOSING_FORMAT: [
                CallbackQueryHandler(
                    choosing_format, pattern=r'^(SRT|VTT|TXT|TXT_W|TXT_GPT|back)$')
            ],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(
            Filters.regex('^(👋 Прощай|👋Прощай|Прощай|done|прощай)$', ), done)],
        name="conversation_with_user",
        persistent=True
    )

    stat_handler = CommandHandler("stat", stat, Filters.user(AUTH))

    broadcast_handler = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast, Filters.user(AUTH)),
        ],
        states={SEND_BROADCAST: [
            MessageHandler(
                Filters.all, send_broadcast)
        ]},
        fallbacks=[CommandHandler("start", start), CommandHandler(
            "broadcast", broadcast), CommandHandler(
            "stat", stat)],
    )

    dispatcher.add_handler(conversation_handler)
    dispatcher.add_handler(stat_handler)
    dispatcher.add_handler(broadcast_handler)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
