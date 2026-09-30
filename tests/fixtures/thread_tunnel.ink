-> room
=== room ===
<- visitor("Ann")
<- visitor("Bo")
+ [Stay] You stay. -> END
=== visitor(name) ===
-> chat(name) ->
After chatting with {name}. -> END
=== chat(who) ===
+ [Chat with {who}] You chat with {who}.
  ->->
