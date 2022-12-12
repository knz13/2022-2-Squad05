import logging
from telegram import Update,InlineKeyboardButton
from telegram.ext import ApplicationBuilder,MessageHandler, ContextTypes, CommandHandler,CallbackQueryHandler
import telegram.ext.filters as filters
import telegram
from telegram.constants import ParseMode
import sqlite3 as sql
import os
from hashlib import sha256
from typing import List



# definindo como o log vai ser salvo
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# dicionario para guardar o id da ultima mensagem mandada p/ cada usuário
# serve para evitar mandarmos muitas mensagens
last_messages = {}

# flags por usuário para controlar em qual estágio da conversa ele está
flags_per_user = {}

# dicionario para guardar os dados temporários quando estiver criando um curso novo
temp_dados_curso = {}


def call_database_and_execute(statement,parameters = []) -> List[sql.Row]:
    """função para auxiliar no uso do banco de dados SQL"""
    db = sql.connect("database.db")
    db.row_factory = sql.Row
    data = db.cursor().execute(statement,parameters)
    
    final_data =  data.fetchall()
    db.commit()
    db.close()
    return final_data

flags = {
    "criando_curso":False,
        "mandando_nome_curso":False,
        "mandando_descricao_curso":False,
        "mandando_senha_curso":False
        #etc
}

def make_sure_flags_are_init(user_id):
    """função auxiliar para garantir que não vamos acessar um usuário não existente"""
    if user_id not in flags_per_user:
        flags_per_user[user_id] = flags



def reset_flags(user_id):
    """função auxiliar para resetar as flags"""
    flags_per_user[user_id] = flags
    if user_id in temp_dados_curso:
        del temp_dados_curso[user_id]

    
# função auxiliar para evitar mudar uma mensagem muito atrás
def reset_last_message(user_id):
    if user_id in last_messages:
        del last_messages[user_id]


async def send_message_or_edit_last(update: Update,context: ContextTypes.DEFAULT_TYPE,text:str,buttons = [],parse_mode = ''):
    """função auxiliar para enviar uma mensagem mais facilmente ou editar a última se possível"""
    if update.effective_chat.id in last_messages:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id,message_id=last_messages[update.effective_chat.id],text=text,reply_markup=telegram.InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        message = await context.bot.send_message(chat_id=update.effective_chat.id,text=text,reply_markup=telegram.InlineKeyboardMarkup(inline_keyboard=buttons),parse_mode=parse_mode)
        last_messages[update.effective_chat.id] = message.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """função chamada quando uma conversa nova é iniciada ou ao mandar um /start"""
    
    data = call_database_and_execute("SELECT * FROM users WHERE user_id = ?",(update.effective_user.id,))
    reset_flags(update.effective_chat.id)
    reset_last_message(update.effective_chat.id)
    message = """Bem vindo ao auto cursos bot!
    
"""
    message += "Sou um bot para criar e administrar cursos pelo Telegram!\n\n"
    if len(data) == 0:
        message += "Gostaria de criar um curso?"
        call_database_and_execute("INSERT INTO users (user_id) VALUES (?)",[update.effective_chat.id])
        await send_message_or_edit_last(update,context,text=message,buttons=[
        [
            telegram.InlineKeyboardButton(text="Sim",callback_data='criar_curso'),
        ],
        [
            telegram.InlineKeyboardButton(text="Não",callback_data='nao_deseja_criar_curso')
        ]
        ])
    else:

        await mostrar_menu_principal(message,update,context)






async def mostrar_menu_principal(message: str,update: Update,context: ContextTypes.DEFAULT_TYPE):
    """
    função para mostrar o menu principal (pode ser chamada em qualquer outra resposta)
    """
    numero_de_cursos = call_database_and_execute("SELECT COUNT(*) FROM cursos WHERE dono_id = ?",[update.effective_chat.id])[0]
    buttons = [
            [
                InlineKeyboardButton(text="criar novo curso",callback_data="criar_curso"),
            ]
        ]
    print(numero_de_cursos["COUNT(*)"])
    if numero_de_cursos["COUNT(*)"] > 0:
        buttons.append([
                InlineKeyboardButton(text='ver seus cursos',callback_data="ver_cursos")
        ])

    await send_message_or_edit_last(update,context,text=message + "Como posso ajudar hoje?",buttons=buttons)



async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função para lidar com mensagens enviadas pelo usuário (respostas ao bot, por exemplo)
    """
    print('calling message handler!')
    make_sure_flags_are_init(update.effective_chat.id)

    if flags_per_user[update.effective_chat.id]['criando_curso']:
        if flags_per_user[update.effective_chat.id]["mandando_nome_curso"]:
            temp_dados_curso[update.effective_chat.id]['nome'] = update.effective_message.text
            await context.bot.send_message(chat_id=update.effective_chat.id,text="Ok! Agora me diga uma breve descrição do seu curso",reply_markup=telegram.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton("voltar ao menu",callback_data="voltar_ao_menu")
                    ]
                ]
            ))
            flags_per_user[update.effective_chat.id]["mandando_nome_curso"] = False
            flags_per_user[update.effective_chat.id]["mandando_descricao_curso"] = True
            reset_last_message(update.effective_chat.id)
            return
        if flags_per_user[update.effective_chat.id]["mandando_descricao_curso"]:
            temp_dados_curso[update.effective_chat.id]['descricao'] = update.effective_message.text
            flags_per_user[update.effective_chat.id]["mandando_descricao_curso"] = False
            flags_per_user[update.effective_chat.id]["mandando_senha_curso"] = True
            await context.bot.send_message(chat_id=update.effective_chat.id,text="Ok! Agora me diga a senha para os alunos entrarem no seu curso",reply_markup=telegram.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton("não desejo colocar",callback_data="nao_deseja_colocar_senha_em_curso")
                    ],
                    [
                        InlineKeyboardButton("voltar ao menu",callback_data="voltar_ao_menu")
                    ]
                ]
            ))
            reset_last_message(update.effective_chat.id)
            return
        if flags_per_user[update.effective_chat.id]["mandando_senha_curso"]:
            temp_dados_curso[update.effective_chat.id]['senha'] = update.effective_message.text
            curso_id = sha256((str(update.effective_chat.id) + "curso" + temp_dados_curso[update.effective_chat.id]['nome']).encode('utf-8')).hexdigest()[:15]
            call_database_and_execute("INSERT INTO cursos (nome,descricao,hash_senha,dono_id,id) VALUES (?,?,?,?,?)",[
                temp_dados_curso[update.effective_chat.id]["nome"],
                temp_dados_curso[update.effective_chat.id]["descricao"],
                sha256(temp_dados_curso[update.effective_chat.id]["senha"].encode('utf-8')).hexdigest(),
                update.effective_chat.id,
                curso_id
            ])
            reset_flags(update.effective_chat.id)
            reset_last_message(update.effective_chat.id)
            await menu_curso(curso_id,update,context)
            return
    


async def menu_curso(id_curso: str,update: Update,context: ContextTypes.DEFAULT_TYPE):
    """
    função para mostrar o menu de um curso específico
    """
    dados_curso = call_database_and_execute("SELECT * FROM cursos WHERE id = ?",[id_curso])
    buttons = [
            [
                InlineKeyboardButton(text="ver id do curso",callback_data=f"receber_id_curso {dados_curso[0]['id']}")
            ],
            [
                InlineKeyboardButton(text="editar nome",callback_data="editar_nome_curso")
            ],
            [
                InlineKeyboardButton(text="editar descrição",callback_data="editar_descricao_curso")
            ],
            [
                InlineKeyboardButton(text="ver aulas cadastradas",callback_data="editar_aulas")
            ],
            [
                InlineKeyboardButton(text="voltar ao menu",callback_data="voltar_ao_menu")
            ],
        ]
    text = f"O que você gostaria de editar?\n\nCurso atual: {dados_curso[0]['nome']}\n\nDescrição do curso: {dados_curso[0]['descricao']}"
    await send_message_or_edit_last(update,context,text=text,buttons=buttons,parse_mode=ParseMode.MARKDOWN_V2)


async def ver_cursos(update: Update,context: ContextTypes.DEFAULT_TYPE):
    """
    função para mostrar todos os cursos já criados
    """
    data = call_database_and_execute("SELECT nome,id FROM cursos WHERE dono_id = ?",[update.effective_chat.id])
    print(list(map(lambda i: len(f'ver_curso_especifico {i["id"]}'.encode('utf-8')),data)))
    buttons = [[InlineKeyboardButton(text=i['nome'],callback_data=f'ver_curso_especifico {i["id"]}')] for i in data]
    buttons.append([InlineKeyboardButton(text="voltar ao menu",callback_data='voltar_ao_menu')])
    await send_message_or_edit_last(update,context,text="Qual curso você deseja editar?",buttons=buttons)
        

async def criar_curso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função para iniciar o diálogo de criação de curso
    """
    make_sure_flags_are_init(update.effective_chat.id)
    if update.effective_chat.id in last_messages:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id,message_id=last_messages[update.effective_chat.id],text="Ok, vamos criar seu curso!\n\nQual título você quer em seu curso?",reply_markup=telegram.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton("voltar ao menu",callback_data="voltar_ao_menu")
                ]
            ]
        ))
        flags_per_user[update.effective_chat.id]['criando_curso'] = True
        flags_per_user[update.effective_chat.id]['mandando_nome_curso'] = True
        temp_dados_curso[update.effective_chat.id] = {"nome":"","descricao":"","senha":""}


async def nao_deseja_criar_curso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função para quando o usuário não deseja criar uma conta ou interagir com o bot agora
    """
    if update.effective_chat.id in last_messages:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id,message_id=last_messages[update.effective_chat.id],text="Tudo certo!\n\nQuando quiser utilizar meus serviços digite /start nesse chat e eu virei te ajudar!\n\nTenha um bom dia :D")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,text="Tudo certo!\n\nQuando quiser utilizar meus serviços digite /start nesse chat e eu virei te ajudar!\n\nTenha um bom dia :D")

async def voltar_ao_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função para voltar ao menu principal (usada como callback dos botões inlines com o callback_data = "voltar_ao_menu")
    """
    reset_flags(update.effective_chat.id)
    await mostrar_menu_principal("",update,context)

async def nao_deseja_senha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função quando o usuário deseja criar um curso sem senha
    """
    curso_id = sha256((str(update.effective_chat.id) + "curso" + temp_dados_curso[update.effective_chat.id]['nome']).encode('utf-8')).hexdigest()[:15]
    call_database_and_execute("INSERT INTO cursos (nome,descricao,hash_senha,dono_id,id) VALUES (?,?,?,?,?)",[
        temp_dados_curso[update.effective_chat.id]["nome"],
        temp_dados_curso[update.effective_chat.id]["descricao"],
        "",
        update.effective_chat.id,
        curso_id
    ])
    reset_flags(update.effective_chat.id)
    await menu_curso(curso_id,update,context)

async def handle_generic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    função para lidar com callbacks genéricos ou que possuem algum dado extra (como id do curso por exemplo)
    """
    print('calling handle generic callback!')
    query = update.callback_query.data
    if len(query.split(' ')) > 1:
        if query.split()[0] == "ver_curso_especifico":
            await menu_curso(query.split()[1],update,context)
            return
        if query.split()[0] == "receber_id_curso":
            await context.bot.send_message(chat_id=update.effective_chat.id,text=query.split()[1])


if __name__ == '__main__':
    
    if not os.path.exists("database.db"):
        #criando o banco de dados caso não exista ainda
        call_database_and_execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )""")

        call_database_and_execute("""
        CREATE TABLE IF NOT EXISTS cursos (
            nome TEXT,
            descricao TEXT,
            dono_id INTEGER,
            hash_senha TEXT,
            id TEXT
        )""")

        call_database_and_execute("""
        CREATE TABLE IF NOT EXISTS aulas_por_curso (
            aula_id TEXT,
            curso_id TEXT,
            descricao TEXT,
            arquivos TEXT
        )""")

        call_database_and_execute("""
        CREATE TABLE IF NOT EXISTS alunos_por_curso (
            aluno_id INTEGER,
            curso_id TEXT,
            aulas_completas TEXT
        )""")

    application = ApplicationBuilder().token('5507439323:AAGiiQ0_vnqIilIRBPRBtGnS54eje4D5xVE').build()
    
    
    

    start_handler = CommandHandler('start', start)

    application.add_handler(start_handler)
    application.add_handler(MessageHandler(callback=message_handler,filters=filters.TEXT))
    application.add_handler(CallbackQueryHandler(callback=criar_curso,pattern='criar_curso'))
    application.add_handler(CallbackQueryHandler(callback=nao_deseja_criar_curso,pattern='nao_deseja_criar_curso'))
    application.add_handler(CallbackQueryHandler(callback=voltar_ao_menu,pattern='voltar_ao_menu'))
    application.add_handler(CallbackQueryHandler(callback=nao_deseja_senha,pattern='nao_deseja_colocar_senha_em_curso'))
    application.add_handler(CallbackQueryHandler(callback=ver_cursos,pattern='ver_cursos'))
    application.add_handler(CallbackQueryHandler(callback=handle_generic_callback))
    
    application.run_polling()