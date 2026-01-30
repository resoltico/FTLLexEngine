# Application strings
-app-name = MyApp

welcome = Welcome to { -app-name }
    .title = Welcome page

user-count = { $count ->
    [0] No users
    [one] One user
   *[other] { $count } users
}

-platform = Web
platform-info = Running on { -platform }
