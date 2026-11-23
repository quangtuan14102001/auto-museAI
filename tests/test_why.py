import asyncio
import edge_tts

async def test_fixed():
    try:
        c = edge_tts.Communicate("Xin chào, tôi là Hoài My, giọng đọc trí tuệ nhân tạo.", "vi-VN-HoaiMyNeural")
        await c.save("output/audio/test_fixed.mp3")
        print("FIXED: Pure voice generated successfully!")
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    asyncio.run(test_fixed())
