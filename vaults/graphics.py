# pip3 install graphviz
from graphviz import Digraph

def generate_graphviz(some_utxo, parameters, output_filename="output.gv"):
    """
    Generate a graphviz dotfile, which can be used to create a
    pictorial/graphical representation of the planned transaction tree.

    legend:
        squares: transactions
        circles: outputs because coins are circular
    """
    (utxos, transactions) = some_utxo.crawl()

    diagram = Digraph("output", filename=output_filename)

    diagram.attr("node", shape="square")
    for transaction in transactions:
        diagram.node(str(transaction.internal_id), transaction.name)

    diagram.attr("node", shape="circle")
    for utxo in utxos:
        diagram.node(str(utxo.internal_id), utxo.name)

        diagram.edge(str(utxo.transaction.internal_id), str(utxo.internal_id))

        for child_transaction in utxo.child_transactions:
            diagram.edge(str(utxo.internal_id), str(child_transaction.internal_id))

    if parameters["enable_graphviz_popup"] == True:
        diagram.view()

    return diagram
