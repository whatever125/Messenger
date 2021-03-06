import json
import sqlite3
import socket
import threading


class Server:
    """Класс сервера, в котором реализовано подключение, регистрация и
    авторизация клиентов, работа с контактами и сообщениями"""
    def __init__(self):
        """Инициализация класса"""
        self.host = 'localhost'
        self.port = 54322
        self.socket = None
        self.clients = []
        self.logins = {}

    def start(self):
        """Запуск сервера"""
        if self.socket:
            raise RuntimeError('Сервер уже запущен')
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.host, self.port))
        self.socket.listen(1024)
        self.socket.settimeout(1000000)
        while True:
            client_socket, address = self.socket.accept()
            t = threading.Thread(target=self.mainloop, args=(client_socket, ))
            t.start()

    def mainloop(self, client_socket):
        """Обработка запросов от клиентов сервера"""
        con = sqlite3.connect("messenger.sql")
        cur = con.cursor()
        self.clients.append(client_socket)
        while True:
            try:
                request = json.loads(client_socket.recv(1024))
                if request['action'] == 'check_online':
                    resp = self.check_online(request, client_socket, con, cur)
                elif request['action'] == 'authorize':
                    resp = self.authorization(request, client_socket, con, cur)
                elif request['action'] == 'register':
                    resp = self.registration(request, con, cur)
                elif request['action'] == 'add_contact':
                    resp = self.add_contact(request, client_socket, con, cur)
                elif request['action'] == 'del_contact':
                    resp = self.del_contact(request, client_socket, con, cur)
                elif request['action'] == 'get_contacts':
                    resp = self.get_contacts(request, client_socket, con, cur)
                elif request['action'] == 'send_message':
                    resp = self.handle_message(request, client_socket, con, cur)
                elif request['action'] == 'get_messages':
                    resp = self.get_messages(request, client_socket, con, cur)
                else:
                    raise RuntimeError(f'Неизвестный запрос: {request["action"]}')
                client_socket.send(bytes(json.dumps(resp), encoding='utf8'))
            except Exception as e:
                client_socket.close()
                self.clients.remove(client_socket)
                try:
                    del self.logins[client_socket]
                except Exception:
                    pass
                break

    def check_online(self, request, client_socket, con, cur):
        """Проверяет, подключен ли пользователь к серверу"""
        resp = {'action': 'response', 'response': 200, 'error': None, 'online': None}
        client_login = request['user']['account_name']
        contact_login = request['user_id']
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {contact_login}'
        elif contact_login in self.logins.values():
            resp['online'] = True
        elif contact_login not in self.logins.values():
            resp['online'] = False
        return resp

    def authorization(self, request, client_socket, con, cur):
        """Авторизация зарегистрированного пользователя"""
        resp = {'action': 'response', 'response': 200, 'error': None}
        client_login = request['user']['account_name']
        client_digest = request['user']['password']
        if not self.check_existence(client_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {client_login}'
        else:
            client_hash = self.get_password(client_login, con, cur)
            if client_hash != client_digest:
                resp['response'] = 403
                resp['error'] = 'Access denied'
            else:
                self.logins[client_socket] = client_login
        return resp

    def registration(self, request, con, cur):
        """Регистрация нового пользователя"""
        resp = {'action': 'response', 'response': 200, 'error': None}
        client_login = request['user']['account_name']
        client_digest = request['user']['password']
        if self.check_existence(client_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'Login is already taken: {client_login}'
        else:
            self.register(client_login, client_digest, con, cur)
        return resp

    def add_contact(self, request, client_socket, con, cur):
        """Добавление клиента в контакты авторизованного пользователя"""
        resp = {'action': 'response', 'response': 200, 'error': None}
        client_login = request['user']['account_name']
        contact_login = request['user_id']
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {contact_login}'
        elif self.in_contacts(client_login, contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'Client already in contacts: {contact_login}'
        else:
            self.add_to_contacts(client_login, contact_login, con, cur)
        return resp

    def del_contact(self, request, client_socket, con, cur):
        """Удаление клиента из контактов авторизованного пользователя"""
        resp = {'action': 'response', 'response': 200, 'error': None}
        client_login = request['user']['account_name']
        contact_login = request['user_id']
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {contact_login}'
        elif not self.in_contacts(client_login, contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'Client not in contacts: {contact_login}'
        else:
            self.del_from_contacts(client_login, contact_login, con, cur)
        return resp

    def get_contacts(self, request, client_socket, con, cur):
        """Возвращает список всех контактов авторизованного пользователя"""
        resp = {'action': 'response', 'response': 200, 'error': None, 'contacts': []}
        client_login = request['user']['account_name']
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(client_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {client_login}'
        else:
            client_contacts = json.loads(self.get_client_contacts(client_login, con, cur))
            resp['contacts'] = client_contacts
        return resp

    def handle_message(self, request, client_socket, con, cur):
        """Обработка сообщения от одного пользователя другому"""
        resp = {'action': 'response', 'response': 200, 'error': None}
        client_login = request['user']['account_name']
        contact_login = request['to']
        message = {'action': 'message', 'from': client_login, 'message': None}
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(contact_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {contact_login}'
        elif contact_login in self.logins.values():
            message['message'] = request['message']
            for socket, login in self.logins.items():
                if login == contact_login:
                    socket.send(bytes(json.dumps(message), encoding='utf8'))
                    break
        elif contact_login not in self.logins.values():
            message['message'] = request['message']
            self.add_unread_messages(contact_login, message, con, cur)
        return resp

    def get_messages(self, request, client_socket, con, cur):
        """Возвращает список сообщений, которые были получены,
        пока пользователь не был в сети"""
        resp = {'action': 'response', 'response': 200, 'error': None, 'messages': []}
        client_login = request['user']['account_name']
        if not self.check_authorization(client_socket, client_login):
            resp['response'] = 403
            resp['error'] = 'Access denied'
        elif not self.check_existence(client_login, con, cur):
            resp['response'] = 400
            resp['error'] = f'No such client: {client_login}'
        else:
            client_contacts = json.loads(self.get_unread_messages(client_login, con, cur))
            resp['messages'] = client_contacts
        return resp

    def register(self, client_login, client_password, con, cur):
        """Регистрация нового пользователя в базе данных"""
        cur.execute("""INSERT INTO users(login, password, contacts, messages) 
                    VALUES(?, ?, '[]', '[]')""", (client_login, client_password))
        con.commit()

    def check_authorization(self, client_socket, client_login):
        """Проверяет, авторизован ли пользователь"""
        if client_socket not in self.logins.keys():
            return False
        return self.logins[client_socket] == client_login

    def check_existence(self, client_login, con, cur):
        """Проверяет, существует ли пользователь в базе данных"""
        return bool(cur.execute("""SELECT login FROM users
                    WHERE login = ?""", (client_login,)).fetchall())

    def get_password(self, client_login, con, cur):
        """Получает сохраненный в базе данных пароль пользователя"""
        return cur.execute("""SELECT password FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0]

    def in_contacts(self, client_login, contact_login, con, cur):
        """Проверяет, есть ли пользователь в контактах"""
        contacts = json.loads(cur.execute("""SELECT contacts FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0])
        return contact_login in contacts

    def add_to_contacts(self, client_login, contact_login, con, cur):
        """Добавляет пользователя в контакты"""
        contacts = json.loads(cur.execute("""SELECT contacts FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0])
        contacts.append(contact_login)
        cur.execute("""UPDATE users
                    SET contacts = ?
                    WHERE login = ?""", (json.dumps(contacts), client_login))
        con.commit()

    def del_from_contacts(self, client_login, contact_login, con, cur):
        """Удаляет пользователя из контактов"""
        contacts = json.loads(cur.execute("""SELECT contacts FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0])
        del contacts[contacts.index(contact_login)]
        cur.execute("""UPDATE users
                    SET contacts = ?
                    WHERE login = ?""", (json.dumps(contacts), client_login))
        con.commit()

    def get_client_contacts(self, client_login, con, cur):
        """Получает список контактов пользователя из базы данных"""
        return cur.execute("""SELECT contacts FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0]

    def add_unread_messages(self, client_login, message, con, cur):
        """Добавляет непрочитанное сообщение в базу данных"""
        messages = json.loads(cur.execute("""SELECT messages FROM users
                    WHERE login = ?""", (client_login,)).fetchone()[0])
        messages.append(message)
        cur.execute("""UPDATE users
                    SET messages = ?
                    WHERE login = ?""", (json.dumps(messages), client_login))
        con.commit()

    def get_unread_messages(self, client_login, con, cur):
        """Получает список непрочитанных сообщений пользователя из базы данных"""
        messages = cur.execute("""SELECT messages FROM users
                            WHERE login = ?""", (client_login,)).fetchone()[0]
        cur.execute("""UPDATE users
                    SET messages = '[]'
                    WHERE login = ?""", (client_login,))
        con.commit()
        return messages


if __name__ == '__main__':
    server = Server()
    server.start()
