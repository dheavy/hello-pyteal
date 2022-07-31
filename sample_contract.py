from pyteal import *

"""Basic counter application"""

def approval_program():
    handle_creation = Seq([
        App.globalPut(Bytes("Count"), Int(0)),
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
        scratch_count.store(App.globalGet(Bytes("Count"))),
        # Increment value in scratch var and update global
        # state variable with it
        App.globalPut(Bytes("Count"), scratch_count.load() + Int(1)),
        Approve()
    )

    decrement = Seq(
        scratch_count.store(App.globalGet(Bytes("Count"))),
        If(
            scratch_count.load() > Int(0),
            App.globalPut(Bytes("Count"), scratch_count.load() - Int(1))
        ),
        Approve()
    )

    handle_noop = Seq(
        # Reject if txn is grouped with others
        Assert(Global.group_size() == Int(1)),

        # Route counter functions
        Cond(
            [Txn.application_args[0] == Bytes("Increment"), increment],
            [Txn.application_args[0] == Bytes("Decrement"), decrement]
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

print(approval_program())
print(clear_state_program())
