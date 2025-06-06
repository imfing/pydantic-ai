from __future__ import annotations as _annotations

import datetime
import os
from typing import Any

import pytest
from dirty_equals import IsInstance
from inline_snapshot import snapshot
from typing_extensions import TypedDict

from pydantic_ai.agent import Agent
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import Usage

from ..conftest import IsDatetime, try_import

with try_import() as imports_successful:
    import boto3

    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.providers.bedrock import BedrockProvider

pytestmark = [
    pytest.mark.skipif(not imports_successful(), reason='bedrock not installed'),
    pytest.mark.anyio,
    pytest.mark.vcr,
]


@pytest.fixture
def bedrock_provider():
    bedrock_client = boto3.client(  # type: ignore[reportUnknownMemberType]
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID', 'AKIA6666666666666666'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', '6666666666666666666666666666666666666666'),
    )
    yield BedrockProvider(bedrock_client=bedrock_client)
    bedrock_client.close()


async def test_bedrock_model(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    assert model.base_url == 'https://bedrock-runtime.us-east-1.amazonaws.com'
    agent = Agent(model=model, system_prompt='You are a chatbot.')

    result = await agent.run('Hello!')
    assert result.data == snapshot(
        "Hello! How can I assist you today? Whether you have questions, need information, or just want to chat, I'm here to help."
    )
    assert result.usage() == snapshot(Usage(requests=1, request_tokens=7, response_tokens=30, total_tokens=37))
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content='You are a chatbot.',
                        timestamp=IsDatetime(),
                    ),
                    UserPromptPart(
                        content='Hello!',
                        timestamp=IsDatetime(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content="Hello! How can I assist you today? Whether you have questions, need information, or just want to chat, I'm here to help."
                    )
                ],
                model_name='us.amazon.nova-micro-v1:0',
                timestamp=IsDatetime(),
            ),
        ]
    )


async def test_bedrock_model_structured_response(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', retries=5)

    class Response(TypedDict):
        temperature: str
        date: datetime.date
        city: str

    @agent.tool_plain
    async def temperature(city: str, date: datetime.date) -> str:
        """Get the temperature in a city on a specific date.

        Args:
            city: The city name.
            date: The date.

        Returns:
            The temperature in degrees Celsius.
        """
        return '30°C'

    result = await agent.run('What was the temperature in London 1st January 2022?', result_type=Response)
    assert result.data == snapshot({'temperature': '30°C', 'date': datetime.date(2022, 1, 1), 'city': 'London'})
    assert result.usage() == snapshot(Usage(requests=2, request_tokens=1236, response_tokens=298, total_tokens=1534))
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content='You are a helpful chatbot.',
                        timestamp=IsDatetime(),
                    ),
                    UserPromptPart(
                        content='What was the temperature in London 1st January 2022?',
                        timestamp=IsDatetime(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content='<thinking> To find the temperature in London on 1st January 2022, I will use the "temperature" tool. I need to provide the date and the city name. The date is already provided as "1st January 2022" and the city name is "London". I will call the "temperature" tool with these parameters.</thinking>\n'
                    ),
                    ToolCallPart(
                        tool_name='temperature',
                        args={'date': '2022-01-01', 'city': 'London'},
                        tool_call_id='tooluse_5WEci1UmQ8ifMFkUcy2gHQ',
                    ),
                ],
                model_name='us.amazon.nova-micro-v1:0',
                timestamp=IsDatetime(),
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='temperature',
                        content='30°C',
                        tool_call_id='tooluse_5WEci1UmQ8ifMFkUcy2gHQ',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content='<thinking> I have received the result from the "temperature" tool. The temperature in London on 1st January 2022 was 30°C. Now, I will use the "final_result" tool to provide this information to the user.</thinking> '
                    ),
                    ToolCallPart(
                        tool_name='final_result',
                        args={'date': '2022-01-01', 'city': 'London', 'temperature': '30°C'},
                        tool_call_id='tooluse_9AjloJSaQDKmpPFff-2Clg',
                    ),
                ],
                model_name='us.amazon.nova-micro-v1:0',
                timestamp=IsDatetime(),
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name='final_result',
                        content='Final result processed.',
                        tool_call_id='tooluse_9AjloJSaQDKmpPFff-2Clg',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
        ]
    )


async def test_bedrock_model_stream(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'temperature': 0.0})
    async with agent.run_stream('What is the capital of France?') as result:
        data = await result.get_data()
    assert data == snapshot(
        'The capital of France is Paris. Paris is not only the capital city but also the most populous city in France, known for its significant cultural, political, and economic influence. It is famous for landmarks such as the Eiffel Tower, the Louvre Museum, and Notre-Dame Cathedral, among many other attractions.'
    )


async def test_bedrock_model_anthropic_model_with_tools(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('anthropic.claude-v2', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'temperature': 0.0})

    @agent.tool_plain
    async def get_current_temperature(city: str) -> str:
        """Get the current temperature in a city.

        Args:
            city: The city name.

        Returns:
            The current temperature in degrees Celsius.
        """
        return '30°C'  # pragma: no cover

    # TODO(Marcelo): Anthropic models don't support tools on the Bedrock Converse Interface.
    # I'm unsure what to do, so for the time being I'm just documenting the test. Let's see if someone complains.
    with pytest.raises(Exception):
        await agent.run('What is the current temperature in London?')


async def test_bedrock_model_anthropic_model_without_tools(
    allow_model_requests: None, bedrock_provider: BedrockProvider
):
    model = BedrockConverseModel('anthropic.claude-v2', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'temperature': 0.0})
    result = await agent.run('What is the capital of France?')
    assert result.data == snapshot('Paris is the capital of France.')


async def test_bedrock_model_retry(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(
        model=model, system_prompt='You are a helpful chatbot.', model_settings={'temperature': 0.0}, retries=2
    )

    @agent.tool_plain
    async def get_capital(country: str) -> str:
        """Get the capital of a country.

        Args:
            country: The country name.
        """
        raise ModelRetry('The country is not supported.')

    result = await agent.run('What is the capital of France?')
    assert result.all_messages() == snapshot(
        [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content='You are a helpful chatbot.',
                        timestamp=IsDatetime(),
                    ),
                    UserPromptPart(
                        content='What is the capital of France?',
                        timestamp=IsDatetime(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content='<thinking> To find the capital of France, I will use the available tool "get_capital". I will input the country name "France" into the tool. </thinking>\n'
                    ),
                    ToolCallPart(
                        tool_name='get_capital',
                        args={'country': 'France'},
                        tool_call_id='tooluse_F8LnaCMtQ0-chKTnPhNH2g',
                    ),
                ],
                model_name='us.amazon.nova-micro-v1:0',
                timestamp=IsDatetime(),
            ),
            ModelRequest(
                parts=[
                    RetryPromptPart(
                        content='The country is not supported.',
                        tool_name='get_capital',
                        tool_call_id='tooluse_F8LnaCMtQ0-chKTnPhNH2g',
                        timestamp=IsDatetime(),
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart(
                        content="""\
<thinking> It seems there was an error in retrieving the capital of France. The tool returned a message saying "The country is not supported." This indicates that the tool does not support the country France. I will inform the user about this limitation and suggest alternative ways to find the information. </thinking>

I'm sorry, but the tool I have does not support retrieving the capital of France. However, I can tell you that the capital of France is Paris. If you need information on a different country, please let me know!\
"""
                    )
                ],
                model_name='us.amazon.nova-micro-v1:0',
                timestamp=IsDatetime(),
            ),
        ]
    )


async def test_bedrock_model_max_tokens(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'max_tokens': 5})
    result = await agent.run('What is the capital of France?')
    assert result.data == snapshot('The capital of France is')


async def test_bedrock_model_top_p(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'top_p': 0.5})
    result = await agent.run('What is the capital of France?')
    assert result.data == snapshot(
        'The capital of France is Paris. Paris is not only the capital city but also the most populous city in France, known for its significant cultural, political, and economic influence both within the country and globally. It is famous for landmarks such as the Eiffel Tower, the Louvre Museum, and the Notre-Dame Cathedral, among many other historical and architectural treasures.'
    )


async def test_bedrock_model_iter_stream(allow_model_requests: None, bedrock_provider: BedrockProvider):
    model = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(model=model, system_prompt='You are a helpful chatbot.', model_settings={'top_p': 0.5})

    @agent.tool_plain
    async def get_capital(country: str) -> str:
        """Get the capital of a country.

        Args:
            country: The country name.
        """
        return 'Paris'  # pragma: no cover

    @agent.tool_plain
    async def get_temperature(city: str) -> str:
        """Get the temperature in a city.

        Args:
            city: The city name.
        """
        return '30°C'  # pragma: no cover

    event_parts: list[Any] = []
    async with agent.iter(user_prompt='What is the temperature of the capital of France?') as agent_run:
        async for node in agent_run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(agent_run.ctx) as request_stream:
                    async for event in request_stream:
                        event_parts.append(event)

    assert event_parts == snapshot(
        [
            PartStartEvent(index=0, part=TextPart(content='<thinking')),
            FinalResultEvent(tool_name=None, tool_call_id=None),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='> To find')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' the temperature')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' of the capital of France,')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' I need to first')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' determine the capital')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' of France and')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' then get')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' the current')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' temperature in')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' that city. The')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' capital of France is Paris')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='. I')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' will use')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' the "get_temperature"')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' tool to find the current temperature')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' in Paris.</')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='thinking')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='>\n')),
            PartStartEvent(
                index=1,
                part=ToolCallPart(
                    tool_name='get_temperature', args='{"city":"Paris"}', tool_call_id='tooluse_lAG_zP8QRHmSYOwZzzaCqA'
                ),
            ),
            IsInstance(FunctionToolCallEvent),
            FunctionToolResultEvent(
                result=ToolReturnPart(
                    tool_name='get_temperature',
                    content='30°C',
                    tool_call_id='tooluse_lAG_zP8QRHmSYOwZzzaCqA',
                    timestamp=IsDatetime(),
                ),
                tool_call_id='tooluse_lAG_zP8QRHmSYOwZzzaCqA',
            ),
            PartStartEvent(index=0, part=TextPart(content='The')),
            FinalResultEvent(tool_name=None, tool_call_id=None),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' current temperature in Paris, the')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' capital of France,')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=' is 30°C')),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='.')),
        ]
    )


@pytest.mark.vcr()
async def test_image_as_binary_content_input(
    allow_model_requests: None, image_content: BinaryContent, bedrock_provider: BedrockProvider
):
    m = BedrockConverseModel('us.amazon.nova-pro-v1:0', provider=bedrock_provider)
    agent = Agent(m, system_prompt='You are a helpful chatbot.')

    result = await agent.run(['What fruit is in the image?', image_content])
    assert result.data == snapshot(
        'The image features a fruit that is round and has a green skin with brown dots. The fruit is cut in half, revealing its interior, which is also green. Based on the appearance and characteristics, the fruit in the image is a kiwi.'
    )


@pytest.mark.vcr()
async def test_image_url_input(allow_model_requests: None, bedrock_provider: BedrockProvider):
    m = BedrockConverseModel('us.amazon.nova-pro-v1:0', provider=bedrock_provider)
    agent = Agent(m, system_prompt='You are a helpful chatbot.')

    result = await agent.run(
        [
            'What is this vegetable?',
            ImageUrl(url='https://t3.ftcdn.net/jpg/00/85/79/92/360_F_85799278_0BBGV9OAdQDTLnKwAPBCcg1J7QtiieJY.jpg'),
        ]
    )
    assert result.data == snapshot(
        'The image shows a potato. It is oval in shape and has a yellow skin with numerous dark brown patches. These patches are known as lenticels, which are pores that allow the potato to breathe. The potato is a root vegetable that is widely cultivated and consumed around the world. It is a versatile ingredient that can be used in a variety of dishes, including mashed potatoes, fries, and potato salad.'
    )


@pytest.mark.vcr()
async def test_document_url_input(allow_model_requests: None, bedrock_provider: BedrockProvider):
    m = BedrockConverseModel('anthropic.claude-v2', provider=bedrock_provider)
    agent = Agent(m, system_prompt='You are a helpful chatbot.')

    document_url = DocumentUrl(url='https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf')

    result = await agent.run(['What is the main content on this document?', document_url])
    assert result.data == snapshot(
        'Based on the provided XML data, the main content of the document is "Dummy PDF file". This is contained in the <document_content> tag for the document with index="1".'
    )


@pytest.mark.vcr()
async def test_text_document_url_input(allow_model_requests: None, bedrock_provider: BedrockProvider):
    m = BedrockConverseModel('anthropic.claude-v2', provider=bedrock_provider)
    agent = Agent(m, system_prompt='You are a helpful chatbot.')

    text_document_url = DocumentUrl(url='https://example-files.online-convert.com/document/txt/example.txt')

    result = await agent.run(['What is the main content on this document?', text_document_url])
    assert result.data == snapshot("""\
Based on the text in the <document_content> tag, the main content of this document appears to be:

An example text describing the use of "John Doe" as a placeholder name in legal cases, hospitals, and other contexts where a party's real identity is unknown or needs to be withheld. It provides background on how "John Doe" and "Jane Doe" are commonly used in the United States and Canada for this purpose, in contrast to other English speaking countries that use names like "Joe Bloggs". The text gives examples of using John/Jane Doe for legal cases, unidentified corpses, and as generic names on forms. It also mentions how "Baby Doe" and "Precious Doe" are used for unidentified children.\
""")


@pytest.mark.vcr()
async def test_text_as_binary_content_input(allow_model_requests: None, bedrock_provider: BedrockProvider):
    m = BedrockConverseModel('us.amazon.nova-pro-v1:0', provider=bedrock_provider)
    agent = Agent(m, system_prompt='You are a helpful chatbot.')

    text_content = BinaryContent(data=b'This is a test document.', media_type='text/plain')

    result = await agent.run(['What is the main content on this document?', text_content])
    assert result.data == snapshot("""\
The document you're referring to appears to be a test document, which means its primary purpose is likely to serve as an example or a placeholder rather than containing substantive content. Test documents are commonly used for various purposes such as:

1. **Software Testing**: To verify that a system can correctly handle, display, or process documents.
2. **Design Mockups**: To illustrate how a document might look in a particular format or style.
3. **Training Materials**: To provide examples for instructional purposes.
4. **Placeholders**: To fill space in a system or application where real content will eventually be placed.

Since this is a test document, it probably doesn't contain any meaningful or specific information beyond what is necessary to serve its testing purpose. If you have specific questions about the format, structure, or any particular element within the document, feel free to ask!\
""")


@pytest.mark.vcr()
async def test_bedrock_empty_system_prompt(allow_model_requests: None, bedrock_provider: BedrockProvider):
    m = BedrockConverseModel('us.amazon.nova-micro-v1:0', provider=bedrock_provider)
    agent = Agent(m)
    result = await agent.run('What is the capital of France?')
    assert result.data == snapshot(
        'The capital of France is Paris. Paris, officially known as "Ville de Paris," is not only the capital city but also the most populous city in France. It is located in the northern central part of the country along the Seine River. Paris is a major global city, renowned for its cultural, political, economic, and social influence. It is famous for its landmarks such as the Eiffel Tower, the Louvre Museum, Notre-Dame Cathedral, and the Champs-Élysées, among many other historic and modern attractions. The city has played a significant role in the history of art, fashion, gastronomy, and science.'
    )
