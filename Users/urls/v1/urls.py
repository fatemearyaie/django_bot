from django.urls import path
from Users.serializer.serializer import users_list
urlpatterns = [
    path('users',users_list, name='user')
]