import base64

from algosdk.future import transaction
from algosdk import account, mnemonic
from algosdk.v2client import algod
from pyteal import *

"""Basic counter application"""

creator_mnemonic = 'detail segment frequent cotton ill zebra month expose patrol gossip simple engine rifle inmate more miss tornado sorry below art sadness join story abstract search'
algod_address = 'http://localhost:4001'
algod_token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'

def compile_program(client, source_code):
    compile_response = client.compile(source_code)
    return base64.b64decode(compile_response['result'])

def get_pv_key_from_mnemonic(mn):
    pv_key = mnemonic.to_private_key(mn)
    return pv_key

def format_state(state):
    formatted = {}
    for item in state:
        key = item['key']
        value = item['value']
        formatted_key = base64.b64decode(key).decode('utf-8')
        if value['type'] == 1:
            if formatted_key == 'voted':
                formatted_value = base64.b64decode(value['bytes']).decode('utf-8')
            else:
                formatted_value = value['bytes']
            formatted[formatted_key] = formatted_value
        else:
            formatted[formatted_key] = value['uint']
    return formatted

def read_global_state(client, app_id):
    app = client.application_info(app_id)
    global_state = app['params']['global-state'] if 'global-state' in app['params'] else []
    return format_state(global_state)

def create_app(client, pv_key, approval_program, clear_program, global_schema, local_schema):
    # Define sender as creator
    sender = account.address_from_private_key(pv_key)

    print('SENDER: {}'.format(sender))

    # Declare on_complete as NoOp
    on_complete = transaction.OnComplete.NoOpOC.real

    # Get node suggested params
    params = client.suggested_params()

    # Create unsigned txn
    txn = transaction.ApplicationCreateTxn(
        sender,
        params,
        on_complete,
        approval_program,
        clear_program,
        global_schema,
        local_schema
    )

    # Sign txn
    signed_txn = txn.sign(pv_key)
    txn_id = signed_txn.transaction.get_txid()

    # Send txn
    client.send_transactions([signed_txn])

    # Wait for confirmation
    try:
        txn_response = transaction.wait_for_confirmation(client, txn_id, 4)
        print('TXN ID', txn_id)
        print('Result confirmed in round: {}'.format(txn_response['confirmed-round']))
    except Exception as err:
        print(err)
        return

    # Display results
    txn_response = client.pending_transaction_info(txn_id)
    app_id = txn_response['application-index']
    print('Create new app-id: {}'.format(app_id))

    return app_id

def approval_program():
    handle_creation = Seq([
        App.globalPut(Bytes('Count'), Int(0)),
        Approve()  # could also be Return(Int(1))
    ])

    handle_optin = Reject()  # could also be Return(Int(0))

    handle_closeout = Reject()

    handle_updateapp = Reject()

    handle_deleteapp = Reject()

    scratch_count = ScratchVar(TealType.uint64)

    increment = Seq(
        # Initial 'store' for the scratch var sets value to
        # current value of the 'Count' global state variable
        scratch_count.store(App.globalGet(Bytes('Count'))),
        # increment value in scratch var and update global
        # state variable with it
        App.globalPut(Bytes('Count'), scratch_count.load() + Int(1)),
        Approve()
    )

    decrement = Seq(
        scratch_count.store(App.globalGet(Bytes('Count'))),
        If(
            scratch_count.load() > Int(0),
            App.globalPut(Bytes('Count'), scratch_count.load() - Int(1))
        ),
        Approve()
    )

    handle_noop = Seq(
        # Reject if txn is grouped with others
        Assert(Global.group_size() == Int(1)),

        # Route counter functions
        Cond(
            [Txn.application_args[0] == Bytes('Increment'), increment],
            [Txn.application_args[0] == Bytes('Decrement'), decrement]
        )
    )

    program = Cond(
        [Txn.application_id() == Int(0), handle_creation],
        [Txn.on_completion() == OnComplete.OptIn, handle_optin],
        [Txn.on_completion() == OnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication, handle_updateapp],
        [Txn.on_completion() == OnComplete.DeleteApplication, handle_deleteapp],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop]
    )

    return compileTeal(program, Mode.Application, version=5)

def clear_state_program():
    program = Approve()
    return compileTeal(program, Mode.Application, version=5)

def main():
    algod_client = algod.AlgodClient(algod_token, algod_address)
    creator_pv_key = get_pv_key_from_mnemonic(creator_mnemonic)

    # Declare (immutable) application state storage
    local_ints = 0
    local_bytes = 0
    global_ints = 1
    global_bytes = 0
    local_schema = transaction.StateSchema(local_ints, local_bytes)
    global_schema = transaction.StateSchema(global_ints, global_bytes)

    # Compile programs to TEAL assembly
    with open('./approval.teal', 'w') as f:
        approval_program_teal = approval_program()
        f.write(approval_program_teal)

    with open('./clear.teal', 'w') as f:
        clear_state_program_teal = clear_state_program()
        f.write(clear_state_program_teal)

    # Compile programs to binary
    approval_program_compiled = compile_program(algod_client, approval_program_teal)
    clear_state_program_compiled = compile_program(algod_client, clear_state_program_teal)

    print('--------------------------------------------')
    print('Deploying counter application......')

    # Create new application
    app_id = create_app(
        algod_client,
        creator_pv_key,
        approval_program_compiled,
        clear_state_program_compiled,
        global_schema,
        local_schema
    )

    print('Global state: {}'.format(read_global_state(algod_client, app_id)))

    print('--------------------------------------------')
    print('Calling counter application......')
    app_args = ['Increment']
    call_app(algod_client, creator_pv_key, app_id, app_args)

    print('Global state: {}'.format(read_global_state(algod_client, app_id)))

def call_app(client, pv_key, index, app_args):
    sender = account.address_from_private_key(pv_key)
    params = client.suggested_params()

    txn = transaction.ApplicationNoOpTxn(sender, params, index, app_args)
    signed_txn = txn.sign(pv_key)
    txn_id = signed_txn.transaction.get_txid()

    client.send_transactions([signed_txn])

    try:
        txn_response = transaction.wait_for_confirmation(client, txn_id, 5)
        print('TXID: ', txn_id)
        print('Result confirmed in round: {}'.format(txn_response['confirmed-round']))
    except Exception as err:
        print(err)
        return

    print('Application called')

main()
