import sys
from website import create_app

app = create_app()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "questions":
        print("Running questions script...")
        from website.questions import process_questions
        process_questions('data.csv')  
    else:
        app.run(debug=True)
