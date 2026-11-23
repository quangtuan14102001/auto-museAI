import asyncio
import edge_tts

async def test_text(txt):
    try:
        c = edge_tts.Communicate(txt, "vi-VN-HoaiMyNeural")
        await c.save("output/audio/test_text.mp3")
        print("Success for:", txt[:30])
    except Exception as e:
        print("Failed for:", txt[:30], "->", e)

async def main():
    await test_text("Xin chào các bạn tôi là người Việt Nam")
    await test_text("Sản phẩm áo thun này rất đẹp và thoáng mát")
    await test_text("Xin chào, tôi là Hoài My, giọng đọc trí tuệ nhân tạo.")

if __name__ == "__main__":
    asyncio.run(main())
