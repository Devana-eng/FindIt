from flask import Flask, render_template, request, redirect, session
from werkzeug.utils import secure_filename
import os
import mysql.connector
from datetime import datetime
from difflib import SequenceMatcher


app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = "uploads"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

app.secret_key = "findit_secret_key"




db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="findit_db"
)

print("Database connected successfully!")




def text_similarity(text1, text2):

    if not text1 or not text2:
        return 0

    text1 = str(text1).strip().lower()
    text2 = str(text2).strip().lower()

    if text1 == text2:
        return 1.0

    return SequenceMatcher(
        None,
        text1,
        text2
    ).ratio()




def calculate_match(lost_item, found_item):

   
    item_name_score = 0
    if lost_item[3].strip().lower() == found_item[3].strip().lower():
        item_name_score = 30

  
    category_score = 0
    if lost_item[4].strip().lower() == found_item[4].strip().lower():
        category_score = 25

   
    if category_score == 0:
        return (0, 0, 0, 0, 0, 0)

   
    color_score = 0
    if lost_item[5].strip().lower() == found_item[5].strip().lower():
        color_score = 15

   
    location_score = 0
    if lost_item[6].strip().lower() == found_item[6].strip().lower():
        location_score = 15

    
    date_score = 0

    lost_date = datetime.strptime(
        str(lost_item[7]),
        "%Y-%m-%d"
    )

    found_date = datetime.strptime(
        str(found_item[7]),
        "%Y-%m-%d"
    )

    difference = abs(
        (lost_date - found_date).days
    )

    if difference == 0:
        date_score = 15
    elif difference <= 1:
        date_score = 12
    elif difference <= 3:
        date_score = 8
    elif difference <= 7:
        date_score = 4

    total_score = (
        item_name_score
        + category_score
        + color_score
        + location_score
        + date_score
    )

    return (
        item_name_score,
        category_score,
        color_score,
        location_score,
        date_score,
        total_score
    )



def create_match(lost_item, found_item):

    cursor = db.cursor()

    try:

       
        check_query = """
        SELECT id
        FROM matches
        WHERE lost_item_id = %s
        AND found_item_id = %s
        """

        cursor.execute(
            check_query,
            (
                lost_item[0],
                found_item[0]
            )
        )

        existing_match = cursor.fetchone()

       
        if existing_match:

            print(
                "MATCH ALREADY EXISTS:",
                lost_item[0],
                "<->",
                found_item[0]
            )

            cursor.close()

            return False

     
        scores = calculate_match(
            lost_item,
            found_item
        )

        category_score = scores[1]
        color_score = scores[2]
        location_score = scores[3]
        date_score = scores[4]
        total_score = scores[5]

        
        if total_score < 65:

            cursor.close()

            return False

    
        query = """
        INSERT INTO matches
        (
            lost_item_id,
            found_item_id,
            category_score,
            color_score,
            location_score,
            date_score,
            total_score
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                lost_item[0],
                found_item[0],
                category_score,
                color_score,
                location_score,
                date_score,
                total_score
            )
        )

        match_id = cursor.lastrowid

        
        notification_query = """
        INSERT INTO notifications
        (
            user_id,
            match_id,
            message,
            is_read
        )
        VALUES (%s, %s, %s, %s)
        """

        message = (
            f"Potential match found for your lost item: "
            f"{lost_item[3]} ({total_score}% match)"
        )

        cursor.execute(
            notification_query,
            (
                lost_item[1],
                match_id,
                message,
                0
            )
        )

        db.commit()

        print(
            "MATCH CREATED:",
            lost_item[3],
            "<->",
            found_item[3],
            "| SCORE:",
            total_score,
            "| MATCH ID:",
            match_id
        )

        cursor.close()

        return True

    except Exception as e:

        db.rollback()

        print(
            "MATCH CREATION ERROR:",
            e
        )

        cursor.close()

        return False



def check_for_matches(new_item_id, report_type):

    cursor = db.cursor()

    try:

        

        cursor.execute("""
            SELECT
                id,
                user_id,
                report_type,
                item_name,
                category,
                color,
                location,
                item_date
            FROM items
            WHERE id = %s
        """, (new_item_id,))

        new_item = cursor.fetchone()

        if not new_item:

            cursor.close()

            return

       

        if report_type == "Lost":

            cursor.execute("""
                SELECT
                    id,
                    user_id,
                    report_type,
                    item_name,
                    category,
                    color,
                    location,
                    item_date
                FROM items
                WHERE report_type = 'Found'
                AND id != %s
            """, (new_item_id,))

        else:

            cursor.execute("""
                SELECT
                    id,
                    user_id,
                    report_type,
                    item_name,
                    category,
                    color,
                    location,
                    item_date
                FROM items
                WHERE report_type = 'Lost'
                AND id != %s
            """, (new_item_id,))

        other_items = cursor.fetchall()

        cursor.close()

       

        if not other_items:

            print("No opposite reports available for matching.")

            return

    

        matches_created = 0

        for other_item in other_items:

            if report_type == "Lost":

                lost_item = new_item
                found_item = other_item

            else:

                lost_item = other_item
                found_item = new_item

            scores = calculate_match(
                lost_item,
                found_item
            )

            total_score = scores[5]

           

            if total_score >= 65:

                created = create_match(
                    lost_item,
                    found_item
                )

                if created:

                    matches_created += 1

        print(
            "AUTOMATIC MATCHING COMPLETED.",
            "New matches:",
            matches_created
        )

    except Exception as e:

        print(
            "AUTOMATIC MATCHING ERROR:",
            e
        )

        cursor.close()



@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not name or not email or not password:

            return "All fields are required"

        if password != confirm_password:

            return "Passwords do not match"

        cursor = db.cursor()

        try:

            

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            existing_user = cursor.fetchone()

            if existing_user:

                cursor.close()

                return "Email already registered"

            query = """
            INSERT INTO users
            (name, email, password)
            VALUES (%s, %s, %s)
            """

            cursor.execute(
                query,
                (
                    name,
                    email,
                    password
                )
            )

            db.commit()

            cursor.close()

            return redirect("/login")

        except Exception as e:

            db.rollback()

            cursor.close()

            return f"Registration error: {e}"

    return render_template("register.html")




@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:

            return "Email and password are required"

        cursor = db.cursor()

        query = """
        SELECT id, name
        FROM users
        WHERE email = %s
        AND password = %s
        """

        cursor.execute(
            query,
            (
                email,
                password
            )
        )

        user = cursor.fetchone()

        cursor.close()

        if user:

            session["user_id"] = user[0]
            session["user_name"] = user[1]

            return redirect("/")

        return "Invalid email or password"

    return render_template("login.html")




@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")



@app.route("/")
def home():

    if "user_id" not in session:

        return redirect("/login")

    return render_template(
        "home.html",
        user_name=session.get("user_name")
    )



@app.route("/report", methods=["GET", "POST"])
def report():

    if "user_id" not in session:

        return redirect("/login")

    if request.method == "POST":

        report_type = request.form.get("report_type")
        item_name = request.form.get("item_name")
        category = request.form.get("category")
        color = request.form.get("color")
        location = request.form.get("location")
        item_date = request.form.get("item_date")
        description = request.form.get("description")
        verification_detail = request.form.get("verification_detail")


        if not all([
            report_type,
            item_name,
            category,
            color,
            location,
            item_date
        ]):

            return "Please fill all required fields"


        image = request.files.get("image")

        image_filename = None

        if image and image.filename:

            image_filename = secure_filename(
                image.filename
            )

            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_filename
            )

            image.save(image_path)


        cursor = db.cursor()

        query = """
INSERT INTO items
(
    user_id,
    report_type,
    item_name,
    category,
    color,
    location,
    item_date,
    description,
    verification_detail,
    image,
    status
)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                session["user_id"],
                report_type,
                item_name,
                category,
                color,
                location,
                item_date,
                description,
                verification_detail,
                image_filename,
                "Reported"
            )
        )

        new_item_id = cursor.lastrowid

        db.commit()

        cursor.close()


        check_for_matches(
            new_item_id,
            report_type
        )

        return redirect("/")

    return render_template(
        "report.html",
        user_name=session.get("user_name")
    )



@app.route("/my-items")
def my_items():

    if "user_id" not in session:

        return redirect("/login")

    cursor = db.cursor()

    query = """
    SELECT
        id,
        report_type,
        item_name,
        category,
        color,
        location,
        item_date,
        description,
        image,
        status
    FROM items
    WHERE user_id = %s
    ORDER BY created_at DESC
    """

    cursor.execute(
        query,
        (session["user_id"],)
    )

    items = cursor.fetchall()

    cursor.close()

    return render_template(
        "my_items.html",
        items=items,
        user_name=session.get("user_name")
    )


@app.route("/notifications")
def notifications():

    if "user_id" not in session:

        return redirect("/login")

    cursor = db.cursor()

    query = """
    SELECT
        id,
        user_id,
        match_id,
        message,
        is_read,
        created_at
    FROM notifications
    WHERE user_id = %s
    ORDER BY created_at DESC
    """

    cursor.execute(
        query,
        (session["user_id"],)
    )

    notifications = cursor.fetchall()

    cursor.close()

    return render_template(
        "notifications.html",
        notifications=notifications,
        user_name=session.get("user_name")
    )



@app.route("/profile")
def profile():

    if "user_id" not in session:

        return redirect("/login")

    cursor = db.cursor()

    query = """
    SELECT name, email
    FROM users
    WHERE id = %s
    """

    cursor.execute(
        query,
        (session["user_id"],)
    )

    user = cursor.fetchone()

    cursor.close()

    if not user:

        session.clear()

        return redirect("/login")

    return render_template(
        "profile.html",
        user_name=user[0],
        user_email=user[1]
    )



@app.route("/matches")
def matches():

    if "user_id" not in session:

        return redirect("/login")

    verify_match_id = request.args.get("verify")

    cursor = db.cursor()

    query = """
    SELECT
        m.id,
        m.total_score,
        m.created_at,

        l.item_name,
        l.category,
        l.color,
        l.location,
        l.item_date,

        f.item_name,
        f.category,
        f.color,
        f.location,
        f.item_date,

        l.status,
        f.status,

        CASE
            WHEN v.verified = 1 THEN 1
            ELSE 0
        END AS is_verified

    FROM matches m

    JOIN items l
        ON m.lost_item_id = l.id

    JOIN items f
        ON m.found_item_id = f.id

    LEFT JOIN verification v
        ON m.id = v.match_id
        AND v.verified = 1

    WHERE m.total_score >= 65

    AND (
        l.user_id = %s
        OR
        f.user_id = %s
    )

    ORDER BY m.total_score DESC
    """

    cursor.execute(
        query,
        (
            session["user_id"],
            session["user_id"]
        )
    )

    matches = cursor.fetchall()

    cursor.close()

    return render_template(
        "matches.html",
        matches=matches,
        user_name=session.get("user_name"),
        verify_match_id=verify_match_id
    )



@app.route("/verify", methods=["POST"])
def verify():

    if "user_id" not in session:
        return redirect("/login")

    match_id = request.form.get("match_id")

    answer = request.form.get(
        "verification_answer",
        ""
    ).strip().lower()

    cursor = db.cursor()

    query = """
    SELECT
        l.verification_detail
    FROM matches m

    JOIN items l
        ON m.lost_item_id = l.id

    WHERE m.id = %s
    """

    cursor.execute(
        query,
        (match_id,)
    )

    item = cursor.fetchone()

    if not item:

        cursor.close()

        return "Match not found"

    correct_answer = str(
        item[0]
    ).strip().lower()

   
    if answer == correct_answer:

        insert_query = """
        INSERT INTO verification
        (
            match_id,
            question1,
            answer1,
            question2,
            answer2,
            question3,
            answer3,
            verified
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        """

        cursor.execute(
            insert_query,
            (
                match_id,

                "What private identifying detail did you provide for this item?",
                answer,

                "",
                "",

                "",
                "",

                1
            )
        )

        update_query = """
        UPDATE items
        SET status = 'Verified'
        WHERE id IN
        (
            SELECT lost_item_id
            FROM matches
            WHERE id = %s
        )
        OR id IN
        (
            SELECT found_item_id
            FROM matches
            WHERE id = %s
        )
        """

        cursor.execute(
            update_query,
            (
                match_id,
                match_id
            )
        )

        db.commit()

        cursor.close()

        return """
        <h2>Ownership Verified Successfully!</h2>

        <p>
            The private identifying detail matched.
        </p>

        <a href="/matches">
            Back to Matches
        </a>
        """

    else:

        cursor.close()

        return """
        <h2>Verification Failed</h2>

        <p>
            The identifying detail does not match.
        </p>

        <a href="/matches?verify=%s">
            Try Again
        </a>
        """ % match_id


if __name__ == "__main__":

    app.run(debug=True)