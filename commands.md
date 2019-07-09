```
register_main - Register the main chat (can create calendar events and is the admin chat)
unregister_main - Unregisters this chat as the main chat (now every other chat has the possibility to become the main chat)
delete_chat - Deletes all data associated with this chat (admin command)
remind_me - Show the attendance keyboard
remind_all - Show attendance keyboards for all known chats (admin command)
show_dice - Show the dice keyboard
reset - Resets all keyboards and the current event in the current chat
reset_all - Reset all keyboards and the current event for all chats (admin command)
status - Returns the chat id ([{id}])
version - Returns the SHA1 of the current commit
server_time - Time on the server (debugging purposes)
users - Shows every user in the chat who has participated in the chat at some time (format: <Name | Roll (jumbo) | muted>)
price_stats - Shows every user with his associated price statistics ({user}: {attendance}/{price} = {attendance/price})
get_data - Returns the state representation for the current chat as a file ({chat.title}.json)
add_insult - Adds an insult which is sent, when someone is not attending ({username} is replaced with the name of the user) (chat_admin command)
```
