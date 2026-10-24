"""Localize generated scaffolding; the model follows the source language itself."""
import re


def chinese_source(text: str) -> bool:
    han = len(re.findall(r'[\u3400-\u9fff]', text))
    latin = len(re.findall(r'[A-Za-z]', text))
    return han > 0 and han * 2 >= latin


SOURCE_LANGUAGE = """
SOURCE LANGUAGE (mandatory): Use the dominant original spoken language of the
transcript for the entire reading edition: overview, headings, explanations,
tables and conclusions. An English transcript requires English notes; a Chinese
transcript requires Chinese notes. Do not translate based on the episode title,
interface language, examples in this prompt, or the language of these instructions.
For mixed speech use its dominant language and retain original quoted passages
and technical terms verbatim. Localize all example headings to that language.
"""
