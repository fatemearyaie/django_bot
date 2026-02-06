from rest_framework.decorators import api_view
from rest_framework.response import Response
from Users.models import CustomUser


@api_view(['GET'])
def users_list(request):
    users = CustomUser.objects.all()
    data = [
        {
        'username':user.username,
        'email':user.email
        }
        for user in users
    ]

    return Response(data)
