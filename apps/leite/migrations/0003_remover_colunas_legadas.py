from django.db import migrations


def _remover_coluna_se_existir(schema_editor, tabela: str, coluna: str) -> None:
    conexao = schema_editor.connection
    with conexao.cursor() as cursor:
        colunas = {
            item.name for item in conexao.introspection.get_table_description(cursor, tabela)
        }
        if coluna not in colunas:
            return
        restricoes = conexao.introspection.get_constraints(cursor, tabela)

    citar = schema_editor.quote_name
    for nome, dados in restricoes.items():
        if dados.get("index") and dados.get("columns") == [coluna]:
            schema_editor.execute(f"DROP INDEX IF EXISTS {citar(nome)}")
    schema_editor.execute(f"ALTER TABLE {citar(tabela)} DROP COLUMN {citar(coluna)}")


def remover_colunas_legadas(apps, schema_editor) -> None:
    _remover_coluna_se_existir(
        schema_editor,
        "leite_producaoanimal",
        "lactacao_id",
    )
    _remover_coluna_se_existir(
        schema_editor,
        "leite_destinoleite",
        "tratamento_id",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("leite", "0002_atualiza_turnos_ordenha"),
    ]

    operations = [
        migrations.RunPython(
            remover_colunas_legadas,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
