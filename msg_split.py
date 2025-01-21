from typing import Generator, List, Tuple, Union
from bs4 import BeautifulSoup, NavigableString, Tag

BLOCK_TAGS = {"p", "b", "strong", "i", "ul", "ol", "div", "span"}

class SplitMessageError(Exception):
    """Исключение, если не удаётся уложить тег или текст в max_len без разрыва."""


def split_message(source: str, max_len: int = 4096) -> Generator[str, None, None]:
    """
    Разбивает исходный HTML-файл на фрагменты не длиннее `max_len`.
    Допускается закрывать/открывать заново только теги из BLOCK_TAGS.
    Если неблочный тег (например, <a>) не влезает целиком, выбрасываем SplitMessageError.
    """
    soup = BeautifulSoup(source, "html.parser")

    # Часто у BeautifulSoup появляется корневой [document] / <html> / <body>.
    # Чтобы не обрабатывать эти лишние теги, возьмём child верхнего уровня.
    top_level_nodes = []
    for child in soup.contents:
        # Игнорируем document/html/body, если попадутся
        if child.name in ("html", "body", "[document]"):
            top_level_nodes.extend(child.contents)
        else:
            top_level_nodes.append(child)

    # Превращаем все верхнеуровневые узлы (в том числе и дочерние) в единый список токенов
    tokens = []
    for node in top_level_nodes:
        tokens.extend(_flatten_soup(node))

    current_tokens: List[Tuple[str, Union[str, dict]]] = []
    open_stack: List[Tuple[str, dict]] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        ttype, data = token

        if ttype == "start_tag":
            tag_name, attrs = data

            if tag_name in BLOCK_TAGS:
                # Блочный тег можно закрывать при переходе между фрагментами.
                # Проверим, влезет ли он, если добавить его прямо сейчас.
                if _length_with_token(current_tokens, token) > max_len:
                    # Закрыть предыдущий фрагмент, если он не пуст
                    if current_tokens:
                        yield _close_and_yield_fragment(current_tokens, open_stack)
                        current_tokens = []
                        open_stack = []

                    # Проверяем, не слишком ли длинный сам по себе тег <p> (или другой)
                    if _length_with_token([], token) > max_len:
                        raise SplitMessageError(
                            f"Блочный тег <{tag_name}> не влезает даже в пустой фрагмент!"
                        )

                # Добавляем тег
                current_tokens.append(token)
                open_stack.append((tag_name, attrs))
                i += 1

            else:
                # Неблочный тег: <a>, <span ...> (если span не в BLOCK_TAGS), <img>, ...
                # Его нельзя рвать — нужно взять целиком подсписок (от start_tag до matching end_tag).
                sub_tokens = _collect_tag_subtree(tokens, i)
                sub_html_len = _tokens_length(sub_tokens)

                if sub_html_len > max_len:
                    # Тег со всем содержимым не влезает ни в один фрагмент => ошибка
                    raise SplitMessageError(
                        f"Тег <{tag_name}> (неблочный) со всем содержимым "
                        f"длиной {sub_html_len} > max_len={max_len}"
                    )

                # Проверяем, влезет ли он в текущий фрагмент (добавим все разом)
                if _length_with_tokens(current_tokens, sub_tokens) > max_len:
                    # Не влезает — значит, закрываем текущий фрагмент
                    if current_tokens:
                        yield _close_and_yield_fragment(current_tokens, open_stack)
                    current_tokens = []
                    open_stack = []

                # Теперь добавляем целиком sub_tokens
                for t in sub_tokens:
                    if t[0] == "start_tag":
                        tg_name, tg_attrs = t[1]
                        open_stack.append((tg_name, tg_attrs))
                    elif t[0] == "end_tag":
                        tg_name = t[1]
                        # снимаем со стека всё вплоть до tg_name
                        idx = None
                        for j in range(len(open_stack) - 1, -1, -1):
                            if open_stack[j][0] == tg_name:
                                idx = j
                                break
                        if idx is not None:
                            open_stack = open_stack[:idx]
                    current_tokens.append(t)

                # Перескочим все сабтокены в исходном списке
                i += len(sub_tokens)

        elif ttype == "end_tag":
            tag_name = data
            # Если это закрывающий блочный тег (tag_name in BLOCK_TAGS), тогда можем закрыть его
            # прямо здесь, но учтём лимит длины.
            if _length_with_token(current_tokens, token) > max_len:
                # Сбрасываем фрагмент
                if current_tokens:
                    yield _close_and_yield_fragment(current_tokens, open_stack)
                    current_tokens = []
                    open_stack = []

                if _length_with_token([], token) > max_len:
                    raise SplitMessageError(
                        f"Закрывающий блочный тег </{tag_name}> сам по себе "
                        f"превышает {max_len} символов"
                    )

            current_tokens.append(token)
            # Снимаем соответствующий открывающий тег со стека
            idx = None
            for j in range(len(open_stack) - 1, -1, -1):
                if open_stack[j][0] == tag_name:
                    idx = j
                    break
            if idx is not None:
                open_stack = open_stack[:idx]

            i += 1

        elif ttype == "text":
            text_data = data
            # Попробуем добавить
            if _length_with_token(current_tokens, token) <= max_len:
                current_tokens.append(token)
                i += 1
            else:
                if not current_tokens:
                    # Если фрагмент пуст, а текст всё равно не влезает, значит текст > max_len
                    # Прямо рвём его
                    piece = text_data[:max_len]
                    current_tokens.append(("text", piece))
                    yield _close_and_yield_fragment(current_tokens, open_stack)
                    current_tokens = []
                    text_data = text_data[max_len:]
                    # продолжаем обрабатывать оставшийся текст
                    # вставим его обратно в tokens (чтобы переработать)
                    tokens.insert(i + 1, ("text", text_data))
                    i += 1
                else:
                    # Закрываем текущий фрагмент
                    yield _close_and_yield_fragment(current_tokens, open_stack)
                    current_tokens = []
                    # Текст всё ещё не обработан, повторим без увеличения i
                # не увеличиваем i, так как либо мы вставили новый токен, либо 
                # сейчас идёт повторная итерация
        else:
            # неизвестный тип
            i += 1

    # Если остались токены — формируем последний фрагмент
    if current_tokens:
        yield _close_and_yield_fragment(current_tokens, open_stack)


def _flatten_soup(node) -> List[Tuple[str, Union[str, dict]]]:
    """
    Рекурсивно преобразует дерево BeautifulSoup в список токенов вида:
      ("start_tag", (tag_name, {attrs})) | ("end_tag", tag_name) | ("text", "...")
    """
    result = []
    if isinstance(node, NavigableString):
        text = str(node)
        if text:
            result.append(("text", text))
    elif isinstance(node, Tag):
        # Открывающий
        result.append(("start_tag", (node.name, dict(node.attrs))))
        for child in node.children:
            result.extend(_flatten_soup(child))
        # Закрывающий
        result.append(("end_tag", node.name))
    return result


def _collect_tag_subtree(tokens: List[Tuple[str, Union[str, dict]]], start_index: int) -> List[Tuple[str, Union[str, dict]]]:
    """
    Собирает подсписок токенов, соответствующих одному цельному тегу + содержимое:
    от первого start_tag (tokens[start_index]) до matching end_tag, **с учётом вложенности**.
    
    Предполагается, что tokens[start_index] – это ("start_tag", (...)).
    """
    subtree = []
    ttype, data = tokens[start_index]
    if ttype != "start_tag":
        return [tokens[start_index]]  # fallback

    # Имя тега, который мы ищем, чтобы закрыть
    main_tag_name = data[0]
    open_count = 0
    i = start_index
    while i < len(tokens):
        t = tokens[i]
        subtree.append(t)
        if t[0] == "start_tag" and t[1][0] == main_tag_name:
            open_count += 1
        elif t[0] == "end_tag" and t[1] == main_tag_name:
            open_count -= 1
            if open_count == 0:
                # Закрыли нужный тег
                break
        i += 1
    return subtree


def _tokens_to_html(tokens: List[Tuple[str, Union[str, dict]]]) -> str:
    """Преобразуем список токенов обратно в строку HTML."""
    parts = []
    for t in tokens:
        ttype, data = t
        if ttype == "start_tag":
            tag_name, attrs = data
            attr_str = ""
            if attrs:
                attr_list = []
                for k, v in attrs.items():
                    if isinstance(v, list):
                        v = " ".join(v)
                    attr_list.append(f'{k}="{v}"')
                if attr_list:
                    attr_str = " " + " ".join(attr_list)
            parts.append(f"<{tag_name}{attr_str}>")
        elif ttype == "end_tag":
            tag_name = data
            parts.append(f"</{tag_name}>")
        elif ttype == "text":
            parts.append(data)
    return "".join(parts)


def _tokens_length(tokens: List[Tuple[str, Union[str, dict]]]) -> int:
    """Подсчитывает суммарную длину HTML, если склеить все токены."""
    return len(_tokens_to_html(tokens))


def _length_with_token(
    current_tokens: List[Tuple[str, Union[str, dict]]],
    new_token: Tuple[str, Union[str, dict]]
) -> int:
    """Вернёт длину HTML, если к current_tokens добавить ещё один new_token."""
    return _tokens_length(current_tokens + [new_token])


def _length_with_tokens(
    current_tokens: List[Tuple[str, Union[str, dict]]],
    new_tokens: List[Tuple[str, Union[str, dict]]]
) -> int:
    """Вернёт длину HTML, если к current_tokens добавить список new_tokens."""
    return _tokens_length(current_tokens + new_tokens)


def _close_and_yield_fragment(
    current_tokens: List[Tuple[str, Union[str, dict]]],
    open_stack: List[Tuple[str, dict]]
) -> str:
    """
    Закрывает все блочные теги, которые остались «открытыми» в open_stack, 
    и возвращает готовый HTML-фрагмент.
    """
    local_tokens = current_tokens[:]
    # Закрываем блочные теги в обратном порядке
    for (tag_name, attrs) in reversed(open_stack):
        if tag_name in BLOCK_TAGS:
            local_tokens.append(("end_tag", tag_name))
    html_fragment = _tokens_to_html(local_tokens)
    return html_fragment
