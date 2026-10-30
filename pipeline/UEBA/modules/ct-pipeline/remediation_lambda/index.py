"""Explicitly disabled until scoped-role ownership and approval are designed."""
def handler(event,context):
    return {'ok':False,'status':'disabled','applied':False,
            'reason':'scoped_role_and_target_binding_required'}
